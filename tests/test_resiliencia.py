"""Testes de resiliência do consumo da origem (tarefa 5.8) — regra 12.

O consumidor REAL é exercitado com httpx.MockTransport (sem rede): retry
com backoff em 5xx (INT-051) e erro de rede (INT-050), 4xx aborta direto,
contrato de paginação R9 (para quando len(itens) < limite; proximo_cursor
= última linha servida; null só em página vazia). No nível do ciclo: origem
sempre indisponível → lote FALHOU após 3 tentativas, cursor não avança.
"""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from conftest import CURSOR_FINAL_PADRAO, NOME_CURSOR, SENTINELA


@pytest.fixture
def consumidor(int_mod, monkeypatch):
    """Consumidor real com backoff sem sleep (testes instantâneos)."""
    mod = int_mod("consumidor")

    async def _sem_sleep(_segundos):
        return None

    monkeypatch.setattr(mod, "asyncio", SimpleNamespace(sleep=_sem_sleep))
    return mod


def _instalar_origem(monkeypatch, mod, handler):
    """Injeta MockTransport no httpx do consumidor (shim do módulo)."""
    cliente_real = httpx.AsyncClient

    def _async_client(**kwargs):
        return cliente_real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(
        mod,
        "httpx",
        SimpleNamespace(AsyncClient=_async_client, HTTPError=httpx.HTTPError),
    )


def _pagina(itens: list, proximo_cursor: str | None) -> dict:
    return {"itens": itens, "proximo_cursor": proximo_cursor}


def _item(n: int) -> dict:
    return {"id_origem": f"item-{n:03d}"}


# -- paginação (R9) ------------------------------------------------------------


def test_pagina_ate_receber_menos_que_o_limite(consumidor, monkeypatch):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        if len(chamadas) == 1:
            return httpx.Response(
                200, json=_pagina([_item(n) for n in range(100)], "2026-10-26T10:00:00Z|100")
            )
        return httpx.Response(
            200, json=_pagina([_item(n) for n in range(50)], "2026-10-26T10:01:00Z|150")
        )

    _instalar_origem(monkeypatch, consumidor, handler)
    itens, cursor_final = asyncio.run(consumidor.consumir_todas_paginas(None))

    assert len(chamadas) == 2  # parou na página parcial
    assert len(itens) == 150
    assert cursor_final == "2026-10-26T10:01:00Z|150"  # último proximo_cursor recebido
    # 2ª página pediu o cursor da última linha servida da 1ª
    assert "cursor=2026-10-26T10%3A00%3A00Z%7C100" in str(chamadas[1].url)
    # API key da origem sempre presente no header
    assert all(r.headers["X-API-Key"] == "campo-dev-key-001" for r in chamadas)


def test_pagina_unica_parcial_devolve_cursor_da_ultima_linha(consumidor, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_pagina([_item(1)], "2026-10-26T10:00:00Z|1"))

    _instalar_origem(monkeypatch, consumidor, handler)
    itens, cursor_final = asyncio.run(consumidor.consumir_todas_paginas(SENTINELA))
    assert len(itens) == 1
    assert cursor_final == "2026-10-26T10:00:00Z|1"


def test_origem_vazia_devolve_sem_itens_e_cursor_nulo(consumidor, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_pagina([], None))

    _instalar_origem(monkeypatch, consumidor, handler)
    itens, cursor_final = asyncio.run(consumidor.consumir_todas_paginas(None))
    assert itens == []
    assert cursor_final is None


# -- retry/backoff (regra 12) ---------------------------------------------------


def test_recupera_apos_503_intermitente(consumidor, monkeypatch):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        if len(chamadas) <= 2:
            return httpx.Response(503, json={"detalhe": "simulador indisponível"})
        return httpx.Response(200, json=_pagina([_item(1)], "c|1"))

    _instalar_origem(monkeypatch, consumidor, handler)
    itens, _ = asyncio.run(consumidor.consumir_todas_paginas(None))
    assert len(chamadas) == 3  # 2 falhas + 1 sucesso
    assert len(itens) == 1


def test_esgota_tentativas_em_5xx_e_levanta_int051(consumidor, monkeypatch):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return httpx.Response(503, json={"detalhe": "fora do ar"})

    _instalar_origem(monkeypatch, consumidor, handler)
    with pytest.raises(Exception) as exc:
        asyncio.run(consumidor.consumir_todas_paginas(None))
    assert exc.value.codigo == "INT-051"
    assert len(chamadas) == 3  # exatamente MAX_TENTATIVAS_HTTP


def test_esgota_tentativas_em_erro_de_rede_e_levanta_int050(consumidor, monkeypatch):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        raise httpx.ConnectError("origem inacessível")

    _instalar_origem(monkeypatch, consumidor, handler)
    with pytest.raises(Exception) as exc:
        asyncio.run(consumidor.consumir_todas_paginas(None))
    assert exc.value.codigo == "INT-050"
    assert len(chamadas) == 3


def test_4xx_aborta_sem_retry(consumidor, monkeypatch):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return httpx.Response(404, json={"detalhe": "rota errada"})

    _instalar_origem(monkeypatch, consumidor, handler)
    with pytest.raises(Exception) as exc:
        asyncio.run(consumidor.consumir_todas_paginas(None))
    assert exc.value.codigo == "INT-099"
    assert len(chamadas) == 1


def test_resposta_fora_do_contrato_de_paginacao(consumidor, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sem": "contrato"})

    _instalar_origem(monkeypatch, consumidor, handler)
    with pytest.raises(Exception) as exc:
        asyncio.run(consumidor.consumir_todas_paginas(None))
    assert exc.value.codigo == "INT-099"


# -- ciclo completo com origem fora do ar (regra 12 no nível do lote) ------------


def test_ciclo_com_origem_indisponivel_fecha_lote_como_falhou(int_mod, oracle, monkeypatch, consumidor):
    """Origem sempre 503 → lote FALHOU com INT-051 e cursor NÃO avança."""
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return httpx.Response(503, json={"detalhe": "modo indisponível"})

    _instalar_origem(monkeypatch, consumidor, handler)  # consumidor REAL no ciclo
    ciclo = int_mod("ciclo")
    resultado = asyncio.run(ciclo.executar_ciclo())

    assert resultado["status"] == "FALHOU"
    assert resultado["codigo_erro"] == "INT-051"
    assert len(chamadas) == 3  # esgotou as 3 tentativas
    lote = next(l for l in oracle.lotes if l.id == resultado["lote_id"])
    assert lote.status == "FALHOU"
    assert lote.observacao.startswith("INT-051")
    assert oracle.cursors[NOME_CURSOR] == SENTINELA  # cursor não avançou
    assert oracle.registros == []  # nada foi processado
