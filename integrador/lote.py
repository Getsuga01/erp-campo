"""Criação, fechamento e contabilização de lotes (3.8) — INT_LOTE.

Decisão do controller sobre duplicados (FIXA, ver idempotencia.py): o
duplicado NÃO gera nova linha em INT_REGISTRO, apenas incrementa
total_duplicados do lote corrente. Por isso `fechar_lote` recalcula
gravados/rejeitados lendo INT_REGISTRO (fonte de verdade) e recebe o
total de duplicados como parâmetro (contagem do consumo do ciclo);
total_recebidos = gravados + rejeitados + duplicados.

O lote fecha CONCLUIDO mesmo com rejeições (regra 3 do plano) e FALHOU
quando um erro de infraestrutura (origem/banco) abortou o ciclo antes de
processar tudo — nesse caso o cursor não avança e o próximo ciclo repega.
"""
import oracledb

from logger import obter_logger
from oracle_client import transacao, valor_retornado

logger = obter_logger()

STATUS_EM_ANDAMENTO = "EM_ANDAMENTO"
STATUS_CONCLUIDO = "CONCLUIDO"
STATUS_FALHOU = "FALHOU"


def criar_lote(cursor_inicio: str | None) -> int:
    """Insere o cabeçalho do lote EM_ANDAMENTO e retorna o id gerado."""
    with transacao() as conn:
        cur = conn.cursor()
        saida = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            "INSERT INTO INT_LOTE (status, cursor_inicio) "
            "VALUES (:status, :cursor_inicio) RETURNING id INTO :id",
            {"status": STATUS_EM_ANDAMENTO, "cursor_inicio": cursor_inicio, "id": saida},
        )
        lote_id = valor_retornado(saida)
    logger.info("lote criado", extra={"lote_id": lote_id})
    return lote_id


def fechar_lote(
    lote_id: int,
    total_duplicados: int,
    status: str,
    cursor_fim: str | None = None,
    observacao: str | None = None,
) -> dict:
    """Fecha o lote com status CONCLUIDO/FALHOU e retorna o resumo dos totais."""
    with transacao() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT SUM(CASE WHEN status = 'GRAVADO' THEN 1 ELSE 0 END), "
            "       SUM(CASE WHEN status = 'REJEITADO' THEN 1 ELSE 0 END) "
            "  FROM INT_REGISTRO WHERE lote_id = :lote",
            {"lote": lote_id},
        )
        gravados, rejeitados = (int(valor or 0) for valor in cur.fetchone())
        recebidos = gravados + rejeitados + int(total_duplicados)
        cur.execute(
            "UPDATE INT_LOTE "
            "   SET status = :status, fechado_em = SYSDATE, "
            "       total_recebidos = :recebidos, total_gravados = :gravados, "
            "       total_rejeitados = :rejeitados, total_duplicados = :duplicados, "
            "       cursor_fim = :cursor_fim, observacao = :observacao "
            " WHERE id = :lote",
            {
                "status": status,
                "recebidos": recebidos,
                "gravados": gravados,
                "rejeitados": rejeitados,
                "duplicados": int(total_duplicados),
                "cursor_fim": cursor_fim,
                "observacao": (observacao or None) and observacao[:500],
                "lote": lote_id,
            },
        )
    logger.info(f"lote fechado como {status}", extra={"lote_id": lote_id})
    return {
        "lote_id": lote_id,
        "status": status,
        "recebidos": recebidos,
        "gravados": gravados,
        "rejeitados": rejeitados,
        "duplicados": int(total_duplicados),
    }
