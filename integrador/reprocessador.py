"""Reprocessamento da fila com revalidação completa (3.15–3.17).

O job pega itens vencidos com SELECT ... FOR UPDATE SKIP LOCKED (sem
concorrência entre execuções), marca PROCESSANDO e revalida o payload
ORIGINAL com cadastros ATUAIS (o validador consulta o banco a cada
tentativa — nenhum cache entre tentativas).

Sucesso → INSERT APONTAMENTO_CAMPO + registro GRAVADO + fila CONCLUIDA.
Falha → tentativas+1, próxima tentativa pela sequência 5/15/60 min e
INSERT em INT_TENTATIVA; tentativas >= max_tentativas → DEAD_LETTER
(também com tentativa FALHA registrada).

O reprocessamento manual (POST /reprocessar) usa a MESMA função de
processamento por item, diferindo apenas em acionado_por=MANUAL e na
observação com o motivo.
"""
import json

import oracledb

from erros import ErroRejeicao
from fila import enfileirar, intervalo_apos
from gravador import inserir_apontamento
from logger import obter_logger
from oracle_client import sessao, transacao
from validador import validar

logger = obter_logger()


def _pegar_item_vencido() -> tuple[int, int] | None:
    """Claim atômico do próximo item vencido (FOR UPDATE SKIP LOCKED)."""
    with transacao() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT f.id, f.registro_id FROM FILA_REPROCESSAMENTO f "
            " WHERE f.situacao = 'PENDENTE' AND f.proxima_tentativa <= SYSTIMESTAMP "
            "   AND ROWNUM = 1 FOR UPDATE SKIP LOCKED"
        )
        linha = cur.fetchone()
        if linha is None:
            return None
        fila_id, registro_id = int(linha[0]), int(linha[1])
        cur.execute(
            "UPDATE FILA_REPROCESSAMENTO SET situacao = 'PROCESSANDO', atualizado_em = SYSTIMESTAMP "
            " WHERE id = :fila_id",
            {"fila_id": fila_id},
        )
    return fila_id, registro_id


def executar_reprocessamento() -> dict:
    """Job do reprocessador: processa todos os itens vencidos, um a um."""
    resultados: list[dict] = []
    while True:
        item = _pegar_item_vencido()
        if item is None:
            break
        resultado = _processar_item(item[0], item[1])
        resultados.append(resultado)
    if resultados:
        logger.info(f"reprocessador processou {len(resultados)} item(ns)")
    return {"processados": len(resultados), "resultados": resultados}


def reprocessar_manual(registro_ids: list[int], motivo: str, acionado_por: str) -> list[dict]:
    """POST /reprocessar — agenda e executa imediatamente cada registro pedido."""
    observacao = f"{motivo} (por {acionado_por})"[:500]
    return [_reprocessar_um(registro_id, observacao) for registro_id in registro_ids]


def _reprocessar_um(registro_id: int, observacao: str) -> dict:
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, status FROM INT_REGISTRO WHERE id = :registro_id", {"registro_id": registro_id})
        registro = cur.fetchone()
        if registro is None:
            return {"registro_id": registro_id, "resultado": "IGNORADO", "mensagem": "registro não encontrado"}
        cur.execute(
            "SELECT id, situacao FROM FILA_REPROCESSAMENTO WHERE registro_id = :registro_id",
            {"registro_id": registro_id},
        )
        fila = cur.fetchone()
    if registro[1] != "REJEITADO" and (fila is None or fila[1] not in ("PENDENTE", "DEAD_LETTER")):
        return {
            "registro_id": registro_id,
            "resultado": "IGNORADO",
            "mensagem": f"estado inválido para reprocessamento (registro {registro[1]})",
        }
    if fila is None:
        # Registro REJEITADO sem fila (ex.: erro não recuperável) — cria fila nova.
        with transacao() as conn:
            fila_id = enfileirar(conn, registro_id, f"reprocessamento manual: {observacao}", intervalo_min=0)
    else:
        fila_id = int(fila[0])
        era_dead_letter = fila[1] == "DEAD_LETTER"
        with transacao() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE FILA_REPROCESSAMENTO "
                "   SET situacao = 'PENDENTE', "
                "       tentativas = CASE WHEN :resetar = 1 THEN 0 ELSE tentativas END, "
                "       proxima_tentativa = SYSTIMESTAMP, atualizado_em = SYSTIMESTAMP "
                " WHERE id = :fila_id AND situacao IN ('PENDENTE', 'DEAD_LETTER')",
                {"resetar": 1 if era_dead_letter else 0, "fila_id": fila_id},
            )
            if cur.rowcount == 0:
                return {
                    "registro_id": registro_id,
                    "resultado": "IGNORADO",
                    "mensagem": "item em processamento ou já concluído",
                }
    resultado = _processar_item(fila_id, registro_id, "MANUAL", observacao)
    return {"registro_id": registro_id, **resultado}


def _processar_item(
    fila_id: int, registro_id: int, acionado_por: str = "SISTEMA", observacao: str | None = None
) -> dict:
    """Revalida um item da fila e registra o desfecho (SUCESSO/FALHA)."""
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT f.tentativas, f.max_tentativas, r.status, r.id_origem, r.payload_original "
            "  FROM FILA_REPROCESSAMENTO f JOIN INT_REGISTRO r ON r.id = f.registro_id "
            " WHERE f.id = :fila_id",
            {"fila_id": fila_id},
        )
        linha = cur.fetchone()
    if linha is None:
        logger.error("item de fila sem registro correspondente", extra={"lote_id": None, "codigo_erro": "INT-099"})
        return {"fila_id": fila_id, "resultado": "IGNORADO", "mensagem": "fila/registro não encontrado"}
    tentativas, max_tentativas, status, id_origem, payload_original = linha
    tentativas, max_tentativas = int(tentativas), int(max_tentativas)
    if not isinstance(payload_original, str):
        payload_original = payload_original.read()
    if status == "GRAVADO":
        _registrar_sucesso(fila_id, registro_id, id_origem, None, tentativas + 1, acionado_por, observacao)
        return {"fila_id": fila_id, "resultado": "SUCESSO", "mensagem": "registro já estava gravado"}
    try:
        payload = json.loads(payload_original)
    except (json.JSONDecodeError, TypeError) as erro:
        rejeicao = ErroRejeicao("INT-011", f"payload original ilegível: {erro}")
        situacao = _registrar_falha(
            fila_id, registro_id, id_origem, tentativas, max_tentativas, rejeicao, acionado_por, observacao
        )
        return _resultado_falha(fila_id, rejeicao, tentativas + 1, situacao)
    try:
        registro_validado = validar(payload)
    except ErroRejeicao as erro:
        situacao = _registrar_falha(
            fila_id, registro_id, id_origem, tentativas, max_tentativas, erro, acionado_por, observacao
        )
        return _resultado_falha(fila_id, erro, tentativas + 1, situacao)
    _registrar_sucesso(
        fila_id, registro_id, id_origem, registro_validado, tentativas + 1, acionado_por, observacao
    )
    return {"fila_id": fila_id, "resultado": "SUCESSO", "mensagem": "registro gravado no reprocessamento"}


def _resultado_falha(fila_id: int, erro: ErroRejeicao, tentativas: int, situacao: str) -> dict:
    return {
        "fila_id": fila_id,
        "resultado": "FALHA",
        "codigo_erro": erro.codigo,
        "mensagem": erro.mensagem,
        "tentativas": tentativas,
        "situacao": situacao,
    }


def _registrar_sucesso(
    fila_id: int,
    registro_id: int,
    id_origem: str,
    registro_validado,
    numero_tentativa: int,
    acionado_por: str,
    observacao: str | None,
) -> None:
    with transacao() as conn:
        cur = conn.cursor()
        if registro_validado is not None:
            inserir_apontamento(conn, registro_id, registro_validado)
            cur.execute(
                "UPDATE INT_REGISTRO "
                "   SET status = 'GRAVADO', codigo_erro = NULL, mensagem_erro = NULL, "
                "       processado_em = SYSTIMESTAMP "
                " WHERE id = :registro_id",
                {"registro_id": registro_id},
            )
        cur.execute(
            "UPDATE FILA_REPROCESSAMENTO SET situacao = 'CONCLUIDA', atualizado_em = SYSTIMESTAMP "
            " WHERE id = :fila_id",
            {"fila_id": fila_id},
        )
        cur.execute(
            "INSERT INTO INT_TENTATIVA (fila_id, numero_tentativa, resultado, acionado_por, observacao) "
            "VALUES (:fila_id, :numero, 'SUCESSO', :acionado_por, :observacao)",
            {
                "fila_id": fila_id,
                "numero": numero_tentativa,
                "acionado_por": acionado_por,
                "observacao": observacao,
            },
        )
    logger.info(
        "reprocessamento concluído com sucesso",
        extra={"id_origem": id_origem, "codigo_erro": None},
    )


def _registrar_falha(
    fila_id: int,
    registro_id: int,
    id_origem: str,
    tentativas: int,
    max_tentativas: int,
    erro: ErroRejeicao,
    acionado_por: str,
    observacao: str | None,
) -> str:
    nova = tentativas + 1
    situacao = "DEAD_LETTER" if nova >= max_tentativas else "PENDENTE"
    with transacao() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE FILA_REPROCESSAMENTO "
            "   SET tentativas = :nova, situacao = :situacao, "
            "       proxima_tentativa = SYSTIMESTAMP + NUMTODSINTERVAL(:intervalo, 'MINUTE'), "
            "       atualizado_em = SYSTIMESTAMP "
            " WHERE id = :fila_id",
            {"nova": nova, "situacao": situacao, "intervalo": intervalo_apos(tentativas), "fila_id": fila_id},
        )
        cur.execute(
            "UPDATE INT_REGISTRO SET codigo_erro = :codigo, mensagem_erro = :mensagem "
            " WHERE id = :registro_id",
            {"codigo": erro.codigo, "mensagem": erro.mensagem[:500], "registro_id": registro_id},
        )
        cur.execute(
            "INSERT INTO INT_TENTATIVA "
            "  (fila_id, numero_tentativa, resultado, codigo_erro, acionado_por, observacao) "
            "VALUES (:fila_id, :numero, 'FALHA', :codigo, :acionado_por, :observacao)",
            {
                "fila_id": fila_id,
                "numero": nova,
                "codigo": erro.codigo,
                "acionado_por": acionado_por,
                "observacao": observacao,
            },
        )
    logger.warning(
        f"reprocessamento falhou ({'DEAD_LETTER' if situacao == 'DEAD_LETTER' else 'nova tentativa agendada'})",
        extra={"id_origem": id_origem, "codigo_erro": erro.codigo},
    )
    return situacao
