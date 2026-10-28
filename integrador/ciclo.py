"""Orquestração do ciclo de integração (3.13) — o coração do Módulo B.

Fluxo (em STREAMING por página — escalabilidade): ler cursor → consumir
cada página (retry 3x em 5xx/rede) → criar lote na 1ª página com itens →
para cada registro: idempotência → validação → grava OU rejeita (um
registro ruim NÃO derruba o lote — regra 3) → ao fim de todas as
páginas: fechar lote → avançar cursor (SÓ após o lote totalmente
persistido — regra 2). Processar página a página evita acumular um
backlog inteiro da origem em RAM; a idempotência cobre o que já foi
gravado.

Falha de infraestrutura (origem INT-050/051, banco INT-052) fecha o lote
como FALHOU com o código no observacao e o cursor NÃO avança — o
próximo ciclo repega tudo (idempotência cuida dos já processados).

POST /ciclo/executar e o job agendado chamam a MESMA função; um lock
simples evita execuções sobrepostas (job × manual × reprocessador).
As operações síncronas do Oracle (bloqueantes) rodar via
asyncio.to_thread — o event loop da API admin nunca fica preso.
"""
import asyncio
import threading

import oracledb

from consumidor import consumir_paginas
from cursor import avancar_cursor, ler_cursor
from erros import ErroCiclo, ErroRejeicao
from gravador import gravar
from idempotencia import status_existente
from lote import criar_lote, fechar_lote
from logger import obter_logger
from rejeitador import rejeitar
from validador import validar

logger = obter_logger()

_bloqueio = threading.Lock()


async def executar_ciclo() -> dict:
    """Executa um ciclo completo; retorna resumo (JA_EM_ANDAMENTO se travado)."""
    if not _bloqueio.acquire(blocking=False):
        logger.warning("ciclo já em andamento — execução ignorada")
        return {"status": "JA_EM_ANDAMENTO"}
    try:
        return await _executar()
    finally:
        _bloqueio.release()


async def _executar() -> dict:
    try:
        return await _executar_interno()
    except oracledb.Error as erro:
        mensagem = str(erro).splitlines()[0][:400]
        logger.critical(f"ciclo falhou por erro do Oracle: {mensagem}")
        return {
            "status": "FALHOU",
            "lote_id": None,
            "codigo_erro": "INT-052",
            "mensagem": mensagem,
        }


async def _executar_interno() -> dict:
    cursor_inicio = ler_cursor()
    lote_id: int | None = None
    duplicados = 0
    cursor_final: str | None = None
    recebeu_dados = False
    try:
        async for itens, proximo_cursor in consumir_paginas(cursor_inicio):
            if proximo_cursor is not None:
                cursor_final = proximo_cursor
            if not itens:
                continue
            recebeu_dados = True
            if lote_id is None:
                lote_id = await asyncio.to_thread(criar_lote, cursor_inicio)
            for item in itens:
                duplicados += await asyncio.to_thread(_processar_item, lote_id, item)
    except ErroCiclo as erro:
        return _fechar_como_falha(cursor_inicio, duplicados, erro, lote_id)
    except oracledb.Error as erro:
        return _fechar_como_falha(
            cursor_inicio,
            duplicados,
            ErroCiclo("INT-052", str(erro).splitlines()[0][:400]),
            lote_id,
        )
    if not recebeu_dados:
        logger.info("nada novo a consumir na origem")
        return {"status": "SEM_DADOS", "lote_id": None, "consumidos": 0, "cursor_inicio": cursor_inicio}
    resumo = await asyncio.to_thread(
        fechar_lote, lote_id, duplicados, "CONCLUIDO", cursor_fim=cursor_final
    )
    await asyncio.to_thread(avancar_cursor, cursor_final)
    logger.info("ciclo concluído", extra={"lote_id": lote_id})
    return {**resumo, "cursor_inicio": cursor_inicio, "cursor_fim": cursor_final}


def _fechar_como_falha(
    cursor_inicio: str | None, duplicados: int, erro: ErroCiclo, lote_id: int | None = None
) -> dict:
    """Cria/fecha o lote como FALHOU com o código INT-05x no observacao."""
    if lote_id is None:
        try:
            lote_id = criar_lote(cursor_inicio)
        except oracledb.Error as erro_banco:
            logger.critical(f"lote FALHOU não pôde ser criado: {erro_banco}")
            return {"status": "FALHOU", "lote_id": None, "codigo_erro": erro.codigo, "mensagem": erro.mensagem}
    try:
        resumo = fechar_lote(
            lote_id, duplicados, "FALHOU", observacao=f"{erro.codigo}: {erro.mensagem}"[:500]
        )
    except oracledb.Error:
        logger.critical("lote não pôde ser fechado (Oracle indisponível)", extra={"lote_id": lote_id})
        resumo = {"lote_id": lote_id, "status": "FALHOU", "recebidos": None, "gravados": None, "rejeitados": None, "duplicados": duplicados}
    logger.error(
        "ciclo falhou — cursor não avançado",
        extra={"lote_id": lote_id, "codigo_erro": erro.codigo},
    )
    return {**resumo, "cursor_inicio": cursor_inicio, "cursor_fim": None, "codigo_erro": erro.codigo, "mensagem": erro.mensagem}


def _processar_item(lote_id: int, item: object) -> int:
    """Processa um registro consumido; retorna 1 se duplicado, senão 0.

    Um registro inválido NÃO derruba o lote (regra 3): vira rejeição com
    código INT-xxx. Erro do Oracle (INT-052) propaga e aborta o ciclo.
    Erros inesperados são registrados como INT-099 (não recuperável).
    """
    id_origem = item.get("id_origem") if isinstance(item, dict) else None
    if id_origem is None:
        logger.error(
            "payload sem id_origem — impossível rastrear; registro ignorado (fora dos totais do lote)",
            extra={"lote_id": lote_id},
        )
        return 0
    try:
        if status_existente(id_origem) is not None:
            logger.info(
                "id_origem já processado — contabilizado como duplicado",
                extra={"lote_id": lote_id, "id_origem": id_origem},
            )
            return 1
        try:
            registro = validar(item)
        except ErroRejeicao as erro:
            rejeitar(lote_id, item, erro)
            return 0
        gravar(lote_id, registro, item)
        return 0
    except oracledb.Error:
        raise
    except Exception as erro_inesperado:
        logger.exception(
            "erro inesperado ao processar registro",
            extra={"lote_id": lote_id, "id_origem": id_origem},
        )
        try:
            rejeitar(lote_id, item, ErroRejeicao("INT-099", type(erro_inesperado).__name__))
        except oracledb.Error:
            raise
        return 0
