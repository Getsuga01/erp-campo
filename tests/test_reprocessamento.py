"""Testes da fila de reprocessamento (tarefa 5.6) — regras 7, 8 e 9.

- **Regra 7** — retentativa com intervalos crescentes (5/15/60 min)
- **Regra 8** — revalidação com cadastros ATUAIS (sem cache entre tentativas)
- **Regra 9** — dead-letter após esgotar max_tentativas; manual com motivo
"""
from datetime import datetime, timedelta, timezone

import pytest

from conftest import rodar_ciclo


@pytest.fixture
def rejeitado_recuperavel(int_mod, oracle, monkeypatch, payloads):
    """Rejeita um PESAGEM com talhão ausente (INT-002) e devolve o id do registro.

    Devolve o ID (não o objeto): o snapshot/rollback do BancoFake substitui
    os objetos das listas, então asserções posteriores devem re-buscar.
    """
    item = payloads.pesagem(talhao_codigo="TAL-999")
    resultado = rodar_ciclo(int_mod, monkeypatch, [item])
    assert resultado["rejeitados"] == 1
    registro = next(r for r in oracle.registros if r.id_origem == item["id_origem"])
    return registro.id


def _registro(oracle, registro_id):
    return next(r for r in oracle.registros if r.id == registro_id)


def _agora_mais(minutos: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutos)


def _futura(minutos: int) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(minutes=minutos)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")


# -- regra 7: retentativa -----------------------------------------------------


def test_regra7_intervalos_crescentes_da_sequencia(int_mod):
    fila = int_mod("fila")
    assert [fila.intervalo_apos(t) for t in (0, 1, 2, 3, 7)] == [5, 15, 60, 60, 60]


def test_regra7_rejeicao_recuperavel_agenda_primeira_tentativa(
    int_mod, rejeitado_recuperavel, oracle
):
    assert len(oracle.fila) == 1
    item = oracle.fila[0]
    assert item.registro_id == rejeitado_recuperavel
    assert item.situacao == "PENDENTE"
    assert (item.tentativas, item.max_tentativas) == (0, 3)
    # 1ª tentativa agendada para daqui a ~5 minutos
    assert _agora_mais(4) < item.proxima_tentativa <= _agora_mais(6)


def test_regra7_item_agendado_nao_e_pego_antes_da_hora(int_mod, rejeitado_recuperavel, oracle):
    reprocessador = int_mod("reprocessador")
    resultado = reprocessador.executar_reprocessamento()
    assert resultado["processados"] == 0
    assert oracle.fila[0].situacao == "PENDENTE"
    assert len(oracle.tentativas) == 0


def test_regra7_falha_incrementa_tentativa_e_reagenda(int_mod, rejeitado_recuperavel, oracle):
    reprocessador = int_mod("reprocessador")
    oracle.expirar_fila()
    resultado = reprocessador.executar_reprocessamento()

    assert resultado["processados"] == 1
    assert resultado["resultados"][0]["resultado"] == "FALHA"
    assert resultado["resultados"][0]["codigo_erro"] == "INT-002"
    item = oracle.fila[0]
    assert (item.tentativas, item.situacao) == (1, "PENDENTE")  # 1 < max → segue na fila
    assert len(oracle.tentativas) == 1
    assert oracle.tentativas[0].resultado == "FALHA"
    assert _registro(oracle, rejeitado_recuperavel).status == "REJEITADO"


# -- regra 8: revalidação com cadastros atuais --------------------------------


def test_regra8_sucesso_apos_correcao_do_cadastro(int_mod, rejeitado_recuperavel, oracle):
    reprocessador = int_mod("reprocessador")
    oracle.expirar_fila()
    reprocessador.executar_reprocessamento()  # 1ª tentativa falha (TAL-999 ausente)

    oracle.cadastrar_talhao("TAL-999", ativo=1)  # cadastro corrigido ENTRE tentativas
    oracle.expirar_fila()
    resultado = reprocessador.executar_reprocessamento()

    assert resultado["resultados"][0]["resultado"] == "SUCESSO"
    registro = _registro(oracle, rejeitado_recuperavel)
    assert registro.status == "GRAVADO"
    assert registro.codigo_erro is None
    item = oracle.fila[0]
    assert item.situacao == "CONCLUIDA"
    # Apontamento criado com o id do cadastro NOVO (revalidação sem cache)
    talhao_novo_id = oracle.talhoes["TAL-999"][0]
    apontamento = next(a for a in oracle.apontamentos if a.registro_id == registro.id)
    assert apontamento.talhao_id == talhao_novo_id
    sucesos = [t for t in oracle.tentativas if t.resultado == "SUCESSO"]
    assert len(sucesos) == 1
    assert sucesos[0].numero_tentativa == 2


# -- regra 9: dead-letter e reprocessamento manual -----------------------------


def test_regra9_dead_letter_apos_esgotar_tentativas(int_mod, rejeitado_recuperavel, oracle):
    reprocessador = int_mod("reprocessador")
    for _ in range(3):
        oracle.expirar_fila()
        resultado = reprocessador.executar_reprocessamento()
        assert resultado["processados"] == 1

    item = oracle.fila[0]
    assert (item.tentativas, item.situacao) == (3, "DEAD_LETTER")
    falhas = [t for t in oracle.tentativas if t.resultado == "FALHA"]
    assert [t.numero_tentativa for t in falhas] == [1, 2, 3]
    assert all(t.codigo_erro == "INT-002" for t in falhas)
    # Registro permanece REJEITADO — agora definitivo (sem fila ativa)
    assert _registro(oracle, rejeitado_recuperavel).status == "REJEITADO"

    # Dead-letter não é mais pego pelo job automático
    oracle.expirar_fila()
    assert reprocessador.executar_reprocessamento()["processados"] == 0


def test_regra9_manual_reseta_dead_letter_com_motivo(int_mod, rejeitado_recuperavel, oracle):
    reprocessador = int_mod("reprocessador")
    for _ in range(3):
        oracle.expirar_fila()
        reprocessador.executar_reprocessamento()
    assert oracle.fila[0].situacao == "DEAD_LETTER"

    oracle.cadastrar_talhao("TAL-999", ativo=1)
    resultado = reprocessador.reprocessar_manual(
        [rejeitado_recuperavel], "talhao cadastrado no ERP", "analista"
    )

    assert resultado[0]["resultado"] == "SUCESSO"
    item = oracle.fila[0]
    assert item.situacao == "CONCLUIDA"
    assert item.tentativas == 0  # resetado por vir de dead-letter
    manual = [t for t in oracle.tentativas if t.acionado_por == "MANUAL"]
    assert len(manual) == 1
    assert "talhao cadastrado no ERP" in manual[0].observacao
    assert _registro(oracle, rejeitado_recuperavel).status == "GRAVADO"
    assert len(oracle.apontamentos) == 1


def test_regra9_manual_cria_fila_para_rejeitado_definitivo(int_mod, oracle, monkeypatch, payloads):
    reprocessador = int_mod("reprocessador")
    item = payloads.pesagem(data_hora=_futura(30))  # INT-007, não recuperável
    rodar_ciclo(int_mod, monkeypatch, [item])
    registro = next(r for r in oracle.registros if r.id_origem == item["id_origem"])
    assert oracle.fila == []  # definitivo não vai para a fila no ciclo

    resultado = reprocessador.reprocessar_manual([registro.id], "revisão solicitada", "analista")

    # Fila criada na hora; revalidação falha com o MESMO erro definitivo
    assert resultado[0]["resultado"] == "FALHA"
    assert resultado[0]["codigo_erro"] == "INT-007"
    item_fila = oracle.fila[0]
    assert (item_fila.tentativas, item_fila.situacao) == (1, "PENDENTE")


def test_regra9_manual_ignora_estados_invalidos(int_mod, oracle, monkeypatch, payloads):
    reprocessador = int_mod("reprocessador")

    inexistente = reprocessador.reprocessar_manual([9999], "teste", "analista")
    assert inexistente[0]["resultado"] == "IGNORADO"
    assert "não encontrado" in inexistente[0]["mensagem"]

    gravado = payloads.pesagem()
    rodar_ciclo(int_mod, monkeypatch, [gravado])
    registro = next(r for r in oracle.registros if r.id_origem == gravado["id_origem"])
    ja_gravado = reprocessador.reprocessar_manual([registro.id], "teste", "analista")
    assert ja_gravado[0]["resultado"] == "IGNORADO"
    assert "estado inválido" in ja_gravado[0]["mensagem"]
