"""Orquestração do ciclo de integração (3.13) — o coração do Módulo B.

Fluxo: ler cursor → consumir TODAS as páginas (retry 3x em 5xx/rede) →
criar lote → para cada registro: idempotência → validação → grava OU
rejeita (um registro ruim NÃO derruba o lote — regra 3) → fechar lote →
avançar cursor (SÓ após o lote totalmente persistido — regra 2).

Falha de infraestrutura (origem INT-050/051, banco INT-052) fecha o lote
como FALHOU com o código no observacao e o cursor NÃO avança — o
próximo ciclo repega tudo (idempotência cuida dos já processados).

POST /ciclo/executar e o job agendado chamam a MESMA função; um lock
simples evita execuções sobrepostas (job × manual × reprocessador).
"""
import threading

import oracledb

from consumidor import consumir_todas_paginas
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
    try:
        itens, cursor_final = await consumir_todas_paginas(cursor_inicio)
    except ErroCiclo as erro:
        return _fechar_como_falha(cursor_inicio, 0, erro)
    if not itens:
        logger.info("nada novo a consumir na origem")
        return {"status": "SEM_DADOS", "lote_id": None, "consumidos": 0, "cursor_inicio": cursor_inicio}
    lote_id = criar_lote(cursor_inicio)
    duplicados = 0
    try:
        for item in itens:
            duplicados += _processar_item(lote_id, item)
    except oracledb.Error as erro:
        return _fechar_como_falha(
            cursor_inicio,
            duplicados,
            ErroCiclo("INT-052", str(erro).splitlines()[0][:400]),
            lote_id,
        )
    resumo = fechar_lote(lote_id, duplicados, "CONCLUIDO", cursor_fim=cursor_final)
    avancar_cursor(cursor_final)
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
