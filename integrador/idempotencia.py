"""Verificação de idempotência por id_origem (3.10) — regra 1 do plano.

Decisão FIXA do controller sobre duplicados: INT_REGISTRO tem UK em
id_origem, portanto uma segunda ocorrência do MESMO id_origem NÃO pode
gerar um novo INT_REGISTRO (nem APONTAMENTO_CAMPO). Quando o id_origem já
existe — em QUALQUER status (GRAVADO, REJEITADO, ...) — o ciclo apenas
contabiliza o fato como duplicado no total_duplicados do lote corrente.
O registro original preserva o primeiro desfecho, e a conciliação por
INT_REGISTRO permanece 1:1 com apontamentos únicos.
"""
from logger import obter_logger
from oracle_client import sessao

logger = obter_logger()


def status_existente(id_origem: str) -> str | None:
    """Status da primeira (e única) ocorrência do id_origem; None se inédito."""
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM INT_REGISTRO WHERE id_origem = :id_origem", {"id_origem": id_origem})
        linha = cur.fetchone()
    return str(linha[0]) if linha else None
