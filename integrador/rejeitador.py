"""Registro de rejeições com código padronizado (3.12).

INSERT em INT_REGISTRO com status REJEITADO, codigo_erro, mensagem_erro e
o payload original em CLOB. Erros recuperáveis são enfileirados na mesma
transação (FILA_REPROCESSAMENTO, tentativas 0); os não recuperáveis
ficam rejeitados definitivos.

Nota: INT_REGISTRO.tipo tem CHECK/NOT NULL, mas o INT-011 pode vir de um
payload cujo `tipo` seja desconhecido — nesses casos o tipo é persistido
com um valor válido do contrato (fallback documentado) para não perder o
payload original, que permanece íntegro no CLOB.
"""
import json

import oracledb

from erros import ErroRejeicao
from fila import enfileirar
from logger import obter_logger
from models import TipoApontamento
from oracle_client import transacao

logger = obter_logger()

TIPOS_VALIDOS = {tipo.value for tipo in TipoApontamento}


def rejeitar(lote_id: int, payload: object, erro: ErroRejeicao) -> int:
    """Persiste a rejeição e, se recuperável, enfileira para reprocessamento."""
    if not isinstance(payload, dict) or not payload.get("id_origem"):
        raise ValueError("payload sem id_origem — impossível rastrear a rejeição")
    tipo = payload.get("tipo")
    if not isinstance(tipo, str) or tipo not in TIPOS_VALIDOS:
        tipo = TipoApontamento.PESAGEM.value
    with transacao() as conn:
        cur = conn.cursor()
        saida = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            "INSERT INTO INT_REGISTRO "
            "  (lote_id, id_origem, tipo, status, codigo_erro, mensagem_erro, payload_original, origem) "
            "VALUES (:lote_id, :id_origem, :tipo, 'REJEITADO', :codigo_erro, :mensagem, :payload, 'CICLO') "
            "RETURNING id INTO :registro_id",
            {
                "lote_id": lote_id,
                "id_origem": payload["id_origem"],
                "tipo": tipo,
                "codigo_erro": erro.codigo,
                "mensagem": erro.mensagem[:500],
                "payload": json.dumps(payload, ensure_ascii=False),
                "registro_id": saida,
            },
        )
        registro_id = int(saida.getvalue())
        if erro.recuperavel:
            enfileirar(conn, registro_id, erro.mensagem)
    logger.warning(
        "registro rejeitado",
        extra={"lote_id": lote_id, "id_origem": payload["id_origem"], "codigo_erro": erro.codigo},
    )
    return registro_id
