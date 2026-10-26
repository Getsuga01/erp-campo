"""Testes de idempotência por id_origem (tarefa 5.3) — regra 1 do plano.

Reenviar o mesmo lote NÃO pode duplicar nada: sem novo INSERT em
APONTAMENTO_CAMPO nem nova linha em INT_REGISTRO — o reenvio é apenas
contabilizado como duplicado no total_duplicados do lote corrente, e o
desfecho da primeira ocorrência é preservado (idempotencia.py).
"""
import pytest

from conftest import CURSOR_FINAL_PADRAO, rodar_ciclo


def test_reenvio_do_mesmo_lote_nao_duplica_nada(int_mod, oracle, monkeypatch, payloads):
    itens = [payloads.pesagem(), payloads.maquina(), payloads.insumo()]

    resultado1 = rodar_ciclo(int_mod, monkeypatch, itens, cursor_final=CURSOR_FINAL_PADRAO)
    assert resultado1["status"] == "CONCLUIDO"
    assert (resultado1["gravados"], resultado1["rejeitados"], resultado1["duplicados"]) == (3, 0, 0)

    resultado2 = rodar_ciclo(
        int_mod, monkeypatch, itens, cursor_final="2026-10-26T13:00:00Z"
    )
    assert resultado2["status"] == "CONCLUIDO"
    assert (resultado2["gravados"], resultado2["rejeitados"], resultado2["duplicados"]) == (0, 0, 3)

    # Nenhuma linha nova: 3 registros, 3 apontamentos (idênticos ao 1º ciclo)
    assert len(oracle.registros) == 3
    assert len(oracle.apontamentos) == 3
    assert resultado2["recebidos"] == 3


def test_lote_misto_com_novos_e_ja_processados(int_mod, oracle, monkeypatch, payloads):
    primeiro = payloads.pesagem()
    rodar_ciclo(int_mod, monkeypatch, [primeiro])

    novo = payloads.maquina()
    resultado = rodar_ciclo(int_mod, monkeypatch, [primeiro, novo])
    assert (resultado["duplicados"], resultado["gravados"]) == (1, 1)
    assert len(oracle.registros) == 2
    assert len(oracle.apontamentos) == 2


def test_desfecho_original_preservado_no_reenvio(int_mod, oracle, monkeypatch, payloads):
    rejeitado_recuperavel = payloads.pesagem(talhao_codigo="TAL-999")  # INT-002
    gravado = payloads.maquina()
    itens = [rejeitado_recuperavel, gravado]
    rodar_ciclo(int_mod, monkeypatch, itens)

    por_origem = {r.id_origem: r for r in oracle.registros}
    assert por_origem[rejeitado_recuperavel["id_origem"]].status == "REJEITADO"
    assert por_origem[gravado["id_origem"]].status == "GRAVADO"
    itens_fila_antes = len(oracle.fila)

    # Reenvio: duplicados, sem nova rejeição, sem nova fila, sem novo apontamento
    resultado = rodar_ciclo(int_mod, monkeypatch, itens)
    assert (resultado["gravados"], resultado["rejeitados"], resultado["duplicados"]) == (0, 0, 2)
    assert len(oracle.fila) == itens_fila_antes  # recuperável não re-enfileirado
    assert len(oracle.apontamentos) == 1
    por_origem = {r.id_origem: r for r in oracle.registros}
    assert por_origem[rejeitado_recuperavel["id_origem"]].status == "REJEITADO"
    assert por_origem[rejeitado_recuperavel["id_origem"]].codigo_erro == "INT-002"


def test_status_existente_por_id_origem(int_mod, oracle, monkeypatch, payloads):
    idempotencia = int_mod("idempotencia")
    inedito = payloads.pesagem()
    assert idempotencia.status_existente(inedito["id_origem"]) is None

    rodar_ciclo(int_mod, monkeypatch, [inedito])
    assert idempotencia.status_existente(inedito["id_origem"]) == "GRAVADO"
