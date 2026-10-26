"""Testes de falha parcial do lote (tarefa 5.5) — regra 3 do plano.

Um lote com mix de válidos e inválidos fecha CONCLUIDO com rejeições: um
registro ruim NÃO derruba o lote. Cada inválido vira rejeição com código
INT-xxx; recuperáveis entram na fila; o cursor avança normalmente.
"""
from conftest import CURSOR_FINAL_PADRAO, NOME_CURSOR, rodar_ciclo


def _futura(minutos: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (
        datetime.now(timezone.utc) + timedelta(minutes=minutos)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")


def test_lote_misto_fecha_concluido_com_rejeicoes(int_mod, oracle, monkeypatch, payloads):
    itens = [
        payloads.pesagem(),  # válido
        payloads.maquina(),  # válido
        payloads.pesagem(talhao_codigo="TAL-999"),  # INT-002 (recuperável)
        payloads.pesagem(data_hora=_futura(30)),  # INT-007 (definitivo)
        payloads.maquina(horas_maquina=25.0),  # INT-008 (definitivo)
    ]

    resultado = rodar_ciclo(int_mod, monkeypatch, itens, cursor_final=CURSOR_FINAL_PADRAO)

    assert resultado["status"] == "CONCLUIDO"
    assert (resultado["gravados"], resultado["rejeitados"], resultado["duplicados"]) == (2, 3, 0)
    assert resultado["recebidos"] == 5
    assert len(oracle.apontamentos) == 2

    por_origem = {r.id_origem: r for r in oracle.registros}
    assert por_origem[itens[2]["id_origem"]].codigo_erro == "INT-002"
    assert por_origem[itens[3]["id_origem"]].codigo_erro == "INT-007"
    assert por_origem[itens[4]["id_origem"]].codigo_erro == "INT-008"

    # Apenas o erro recuperável entrou na fila; cursor avançou normalmente
    assert len(oracle.fila) == 1
    item = oracle.fila[0]
    assert item.situacao == "PENDENTE"
    assert (item.tentativas, item.max_tentativas) == (0, 3)
    assert oracle.cursors[NOME_CURSOR] == CURSOR_FINAL_PADRAO


def test_lote_concluido_apesar_de_tudo_invalido(int_mod, oracle, monkeypatch, payloads):
    itens = [
        payloads.pesagem(talhao_codigo="TAL-999"),
        payloads.maquina(horas_maquina=25.0),
    ]
    resultado = rodar_ciclo(int_mod, monkeypatch, itens)
    assert resultado["status"] == "CONCLUIDO"
    assert (resultado["gravados"], resultado["rejeitados"]) == (0, 2)
    assert all(r.status == "REJEITADO" for r in oracle.registros)


def test_payload_sem_id_origem_fica_fora_dos_totais(int_mod, oracle, monkeypatch, payloads):
    valido = payloads.pesagem()
    rastreado = payloads.maquina()
    del rastreado["id_origem"]

    resultado = rodar_ciclo(int_mod, monkeypatch, [valido, rastreado])

    assert resultado["status"] == "CONCLUIDO"
    assert (resultado["gravados"], resultado["rejeitados"], resultado["duplicados"]) == (1, 0, 0)
    # Sem id_origem não há rastreio: ignorado sem registro em INT_REGISTRO
    assert len(oracle.registros) == 1
    assert oracle.registros[0].id_origem == valido["id_origem"]
