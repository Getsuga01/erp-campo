"""Gravação do apontamento validado no ERP (3.11) — APONTAMENTO_CAMPO.

Commit POR REGISTRO, não por lote: um problema no meio do lote mantém os
registros anteriores gravados, e o cursor — avançado apenas no fim —
garante o repegar dos restantes no próximo ciclo (duplicados pela
idempotência). A sequência por registro é atômica: INSERT INT_REGISTRO
(status RECEBIDO) → INSERT ERP_SUPRIMENTOS.APONTAMENTO_CAMPO → UPDATE
INT_REGISTRO para GRAVADO. As FKs são resolvidas por código pelo
validador (ids já trazidos no RegistroValidado).

data_hora é normalizada para UTC: o banco guarda TIMESTAMP sem
timezone, e a convenção da demo é "banco em UTC".
"""
import json
from datetime import timezone

import oracledb

from logger import obter_logger
from oracle_client import transacao, valor_retornado
from validador import RegistroValidado

logger = obter_logger()


def _data_utc(registro: RegistroValidado) -> object:
    momento = registro.modelo.data_hora
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc).replace(tzinfo=None)


def inserir_apontamento(conn: oracledb.Connection, registro_id: int, registro: RegistroValidado) -> None:
    """Insere apenas o APONTAMENTO_CAMPO — usado pelo gravador e pelo reprocessador."""
    modelo = registro.modelo
    conn.cursor().execute(
        "INSERT INTO ERP_SUPRIMENTOS.APONTAMENTO_CAMPO "
        "  (registro_id, id_origem, tipo, data_hora, talhao_id, equipamento_id, item_id, "
        "   peso_bruto, peso_tara, peso_liquido, horas_maquina, quantidade, operador, observacao) "
        "VALUES (:registro_id, :id_origem, :tipo, :data_hora, :talhao_id, :equipamento_id, "
        "        :item_id, :peso_bruto, :peso_tara, :peso_liquido, :horas_maquina, "
        "        :quantidade, :operador, :observacao)",
        {
            "registro_id": registro_id,
            "id_origem": modelo.id_origem,
            "tipo": modelo.tipo.value,
            "data_hora": _data_utc(registro),
            "talhao_id": registro.talhao_id,
            "equipamento_id": registro.equipamento_id,
            "item_id": registro.item_id,
            "peso_bruto": modelo.peso_bruto,
            "peso_tara": modelo.peso_tara,
            "peso_liquido": modelo.peso_liquido,
            "horas_maquina": modelo.horas_maquina,
            "quantidade": modelo.quantidade,
            "operador": modelo.operador,
            "observacao": modelo.observacao,
        },
    )


def gravar(lote_id: int, registro: RegistroValidado, payload_original: dict) -> int:
    """Grava o registro (INT_REGISTRO + APONTAMENTO_CAMPO) e retorna o id do registro."""
    modelo = registro.modelo
    with transacao() as conn:
        cur = conn.cursor()
        saida = cur.var(oracledb.DB_TYPE_NUMBER)
        cur.execute(
            "INSERT INTO INT_REGISTRO "
            "  (lote_id, id_origem, tipo, status, payload_original, origem) "
            "VALUES (:lote_id, :id_origem, :tipo, 'RECEBIDO', :payload, 'CICLO') "
            "RETURNING id INTO :registro_id",
            {
                "lote_id": lote_id,
                "id_origem": modelo.id_origem,
                "tipo": modelo.tipo.value,
                "payload": json.dumps(payload_original, ensure_ascii=False),
                "registro_id": saida,
            },
        )
        registro_id = valor_retornado(saida)
        inserir_apontamento(conn, registro_id, registro)
        cur.execute(
            "UPDATE INT_REGISTRO SET status = 'GRAVADO', processado_em = SYSDATE "
            " WHERE id = :registro_id",
            {"registro_id": registro_id},
        )
    logger.info("registro gravado", extra={"lote_id": lote_id, "id_origem": modelo.id_origem})
    return registro_id
