"""Consumo da API da origem com paginação por cursor e retry (3.6).

Contrato de paginação (emenda R9, commit c4f1258): `proximo_cursor` é a
posição da última linha servida semprere que ≥1 item é servido; null só
em página vazia. Regra de consumo: pagina-se até receber página com
len(itens) < limite; o cursor final do ciclo é o ÚLTIMO proximo_cursor
recebido (posição da última linha servida). O cursor do banco só é
avançado pelo ciclo após o lote totalmente persistido — nada de
relógio/t0.

Retry com backoff exponencial: 3 tentativas em 5xx da origem (INT-051)
e timeout/erro de rede (INT-050). Após esgotar, o ciclo marca o lote
FALHOU (regra 12 do plano).
"""
import asyncio

import httpx

from config import obter_settings
from cursor import SENTINELA
from erros import ErroCiclo
from logger import obter_logger

logger = obter_logger()

MAX_TENTATIVAS_HTTP = 3


async def consumir_todas_paginas(cursor_atual: str | None) -> tuple[list[dict], str | None]:
    """Consome todas as páginas pendentes a partir do cursor do banco.

    Retorna (itens, cursor_final): cursor_final é o último
    proximo_cursor recebido — None quando nada foi servido (origem sem
    novidades; o cursor do banco não precisa avançar).
    """
    cfg = obter_settings()
    itens: list[dict] = []
    cursor_final: str | None = None
    cursor_pagina = _cursor_para_request(cursor_atual)
    async with httpx.AsyncClient(
        timeout=cfg.timeout_http_seg, headers={"X-API-Key": cfg.campo_api_key}
    ) as client:
        while True:
            resposta = await _obter_pagina(client, cursor_pagina)
            pagina = _interpretar(resposta)
            itens.extend(pagina["itens"])
            if pagina["proximo_cursor"] is not None:
                cursor_final = pagina["proximo_cursor"]
            if len(pagina["itens"]) < cfg.limite_pagina:
                break
            cursor_pagina = pagina["proximo_cursor"]
    return itens, cursor_final


def _cursor_para_request(cursor: str | None) -> str | None:
    """A sentinela (ou ausência) significa "desde o início" — sem parâmetro."""
    if cursor is None or cursor == SENTINELA:
        return None
    return cursor


async def _obter_pagina(client: httpx.AsyncClient, cursor: str | None) -> httpx.Response:
    """GET /apontamentos com retry (3 tentativas) em 5xx/rede; 4xx aborta."""
    cfg = obter_settings()
    params: dict = {"limite": cfg.limite_pagina}
    if cursor is not None:
        params["cursor"] = cursor
    ultimo_erro: ErroCiclo | None = None
    for tentativa in range(1, MAX_TENTATIVAS_HTTP + 1):
        try:
            resposta = await client.get(f"{cfg.campo_url}/apontamentos", params=params)
        except httpx.HTTPError as erro:
            ultimo_erro = ErroCiclo("INT-050", type(erro).__name__)
        else:
            if resposta.status_code >= 500:
                ultimo_erro = ErroCiclo("INT-051", f"HTTP {resposta.status_code}")
            elif resposta.status_code == 200:
                return resposta
            else:
                raise ErroCiclo("INT-099", f"HTTP inesperado {resposta.status_code} da origem")
        if tentativa < MAX_TENTATIVAS_HTTP:
            await asyncio.sleep(2 ** (tentativa - 1))
    assert ultimo_erro is not None
    logger.error(f"consumo da origem esgotou as tentativas: {ultimo_erro.mensagem}")
    raise ultimo_erro


def _interpretar(resposta: httpx.Response) -> dict:
    """Valida o contrato de paginação da resposta."""
    try:
        pagina = resposta.json()
    except ValueError as erro:
        raise ErroCiclo("INT-099", "resposta da origem não é JSON") from erro
    if not isinstance(pagina, dict) or "itens" not in pagina or "proximo_cursor" not in pagina:
        raise ErroCiclo("INT-099", "contrato de paginação violado pela origem")
    return pagina
