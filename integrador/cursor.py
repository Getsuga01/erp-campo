"""Gerenciamento do cursor incremental seguro (3.7) — INT_CURSOR/CAMPO_API.

Regra 2 do plano: o cursor só avança DEPOIS que o lote inteiro foi
persistido (comitado). Se o integrador cair no meio do processamento, o
cursor antigo faz o próximo ciclo repegar os mesmos registros — a
idempotência por id_origem transforma os já processados em duplicados,
sem efeitos duplicados no ERP. `avancar_cursor` é um UPDATE atômico.
"""
from logger import obter_logger
from oracle_client import sessao, transacao

logger = obter_logger()

NOME_CURSOR = "CAMPO_API"
SENTINELA = "1970-01-01T00:00:00Z"


def ler_cursor() -> str | None:
    """Retorna a posição atual; semeia a sentinela se a linha ainda não existir."""
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute("SELECT posicao FROM INT_CURSOR WHERE nome = :nome", {"nome": NOME_CURSOR})
        linha = cur.fetchone()
        if linha is not None:
            return str(linha[0])
    _semear()
    return SENTINELA


def _semear() -> None:
    logger.warning(f"cursor {NOME_CURSOR} ausente — semeando posição sentinela")
    with transacao() as conn:
        conn.cursor().execute(
            "INSERT INTO INT_CURSOR (nome, posicao) VALUES (:nome, :posicao)",
            {"nome": NOME_CURSOR, "posicao": SENTINELA},
        )


def avancar_cursor(posicao: str) -> None:
    """Atualiza a posição atomicamente — SOMENTE após o lote totalmente persistido."""
    with transacao() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE INT_CURSOR SET posicao = :posicao, atualizado_em = SYSTIMESTAMP "
            "WHERE nome = :nome",
            {"posicao": posicao, "nome": NOME_CURSOR},
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"cursor {NOME_CURSOR} não encontrado para avançar")
    logger.info("cursor avançado", extra={"lote_id": None})
