"""Fila de reprocessamento e dead-letter (3.14) — FILA_REPROCESSAMENTO.

Backoff fixo decidido pelo controller: 1ª tentativa em +5 min, 2ª em
+15 min, 3ª em +60 min; esgotada a sequência, mantém 60 min. O intervalo
é sempre calculado a partir do número de tentativas JÁ feitas.
"""
import oracledb

from config import obter_settings
from logger import obter_logger
from oracle_client import valor_retornado

logger = obter_logger()

BACKOFF_MINUTOS = (5, 15, 60)


def intervalo_apos(tentativas_feitas: int) -> int:
    """Intervalo (min) para agendar a PRÓXIMA tentativa.

    A tentativa nº k usa BACKOFF_MINUTOS[k-1] (1ª=5, 2ª=15, 3ª=60); acima
    disso a sequência esgota e o intervalo fica em 60.
    """
    return BACKOFF_MINUTOS[min(tentativas_feitas, len(BACKOFF_MINUTOS) - 1)]


def enfileirar(conn: oracledb.Connection, registro_id: int, motivo: str, intervalo_min: int | None = None) -> int:
    """Insere item PENDENTE na fila dentro da transação do chamador.

    `intervalo_min=None` usa o backoff da 1ª tentativa (+5 min); o
    reprocessamento manual agenda imediato com intervalo_min=0.
    """
    cfg = obter_settings()
    intervalo = intervalo_apos(0) if intervalo_min is None else intervalo_min
    cur = conn.cursor()
    saida = cur.var(oracledb.DB_TYPE_NUMBER)
    cur.execute(
        "INSERT INTO FILA_REPROCESSAMENTO "
        "  (registro_id, situacao, tentativas, max_tentativas, proxima_tentativa, motivo) "
        "VALUES (:registro_id, 'PENDENTE', 0, :max_tentativas, "
        "        SYSDATE + NUMTODSINTERVAL(:intervalo, 'MINUTE'), :motivo) "
        "RETURNING id INTO :fila_id",
        {
            "registro_id": registro_id,
            "max_tentativas": cfg.max_tentativas,
            "intervalo": intervalo,
            "motivo": motivo[:500],
            "fila_id": saida,
        },
    )
    fila_id = valor_retornado(saida)
    logger.info(f"registro {registro_id} enfileirado para reprocessamento (fila {fila_id})")
    return fila_id
