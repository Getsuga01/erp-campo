"""Testes do validador de contrato e regras de negócio (tarefa 5.2).

Regras do plano cobertas aqui:
- **Regra 4** — peso_liquido = bruto - tara > 0 (INT-006)
- **Regra 5** — cadastros existem e estão ativos (INT-002/003/004/005)
- **Regra 6** — data_hora em UTC, futuro rejeitado com tolerância (INT-007)
- **Regra 7** — erros de cadastro são recuperáveis (flag que alimenta a fila)
- **Regra 8** — horas_maquina em (0, 24] (INT-008)
- **Regra 13** — versao_contrato suportada (INT-009)
"""
import logging
from datetime import datetime, timedelta, timezone

import pytest


def _iso(momento: datetime) -> str:
    return momento.isoformat(timespec="seconds").replace("+00:00", "Z")


def _futuro(minutos: int) -> str:
    return _iso(datetime.now(timezone.utc) + timedelta(minutes=minutos))


@pytest.fixture
def validar(int_mod, oracle):
    return int_mod("validador").validar


@pytest.fixture
def erros_mod(int_mod):
    return int_mod("erros")


# -- happy path --------------------------------------------------------------


def test_pesagem_valida_resolve_fks_por_codigo(validar, payloads):
    registro = validar(payloads.pesagem(talhao_codigo="TAL-007", equipamento_codigo="EQP-009"))
    assert registro.talhao_id == 7
    assert registro.equipamento_id == 9
    assert registro.item_id is None
    assert registro.modelo.peso_liquido == 7000.0


def test_maquina_e_insumo_validos_resolvem_fks(validar, payloads):
    maquina = validar(payloads.maquina(talhao_codigo="TAL-005", equipamento_codigo="EQP-003"))
    assert (maquina.talhao_id, maquina.equipamento_id, maquina.item_id) == (5, 3, None)
    insumo = validar(payloads.insumo(talhao_codigo="TAL-004", item_codigo="ITEM-006"))
    assert (insumo.talhao_id, insumo.item_id) == (4, 6)


def test_campos_extras_desconhecidos_sao_ignorados(validar, payloads, caplog):
    payload = payloads.pesagem()
    payload["campo_surpresa"] = 123
    with caplog.at_level(logging.WARNING, logger="integrador"):
        registro = validar(payload)
    assert registro.modelo.id_origem == payload["id_origem"]
    assert any("desconhecidos" in mensagem for mensagem in caplog.messages)


# -- regra 13: versão do contrato --------------------------------------------


def test_regra13_versao_contrato_nao_suportada(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(versao_contrato="2.0"))
    assert exc.value.codigo == "INT-009"
    assert exc.value.recuperavel is False


# -- regra 6: data futura / UTC ----------------------------------------------


def test_regra6_data_futura_acima_da_tolerancia_rejeita(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(data_hora=_futuro(10)))
    assert exc.value.codigo == "INT-007"


def test_regra6_data_futura_dentro_da_tolerancia_aceita(validar, payloads):
    registro = validar(payloads.pesagem(data_hora=_futuro(2)))
    assert registro.modelo.data_hora is not None


def test_regra6_data_sem_timezone_e_tratada_como_utc(validar, erros_mod, payloads):
    naive_passado = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)
    assert validar(payloads.pesagem(data_hora=naive_passado.isoformat()))
    naive_futuro = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None)
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(data_hora=naive_futuro.isoformat()))
    assert exc.value.codigo == "INT-007"


# -- regra 5: cadastros ------------------------------------------------------


def test_regra5_talhao_inexistente(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(talhao_codigo="TAL-999"))
    assert exc.value.codigo == "INT-002"
    assert exc.value.recuperavel is True  # regra 7: recuperável após correção


def test_regra5_talhao_inativo(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(talhao_codigo="TAL-019"))
    assert exc.value.codigo == "INT-003"
    assert exc.value.recuperavel is True


def test_regra5_equipamento_inexistente(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.maquina(equipamento_codigo="EQP-999"))
    assert exc.value.codigo == "INT-004"
    assert exc.value.recuperavel is True


def test_regra5_equipamento_inativo(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.maquina(equipamento_codigo="EQP-015"))
    assert exc.value.codigo == "INT-004"
    assert exc.value.recuperavel is True


def test_regra5_item_inexistente(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.insumo(item_codigo="ITEM-999"))
    assert exc.value.codigo == "INT-005"
    assert exc.value.recuperavel is True


# -- regra 4: peso ------------------------------------------------------------


def test_regra4_peso_liquido_diferente_de_bruto_menos_tara(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(peso_bruto=10000.0, peso_tara=3000.0, peso_liquido=6500.0))
    assert exc.value.codigo == "INT-006"
    assert exc.value.recuperavel is False


def test_regra4_peso_liquido_zero_ou_negativo(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(peso_bruto=2000.0, peso_tara=3000.0, peso_liquido=-1000.0))
    assert exc.value.codigo == "INT-006"


def test_regra4_tolerancia_de_arredondamento_3_casas(validar, erros_mod, payloads):
    # diferença 0.0009 kg: dentro da tolerância de 0.001
    assert validar(payloads.pesagem(peso_liquido=7000.0009))
    # diferença 0.002 kg: acima da tolerância
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(peso_liquido=7000.002))
    assert exc.value.codigo == "INT-006"


def test_peso_acima_do_limite_alerta_mas_grava(validar, payloads, caplog):
    payload = payloads.pesagem(peso_bruto=70000.0, peso_tara=5000.0, peso_liquido=65000.0)
    with caplog.at_level(logging.WARNING, logger="integrador"):
        registro = validar(payload)
    assert registro.modelo.peso_bruto == 70000.0
    assert any("limite de alerta" in mensagem for mensagem in caplog.messages)


# -- regra 8: horas_maquina ---------------------------------------------------


@pytest.mark.parametrize("horas", [25.0, 0.0, -1.5, 24.01])
def test_regra8_horas_maquina_fora_do_intervalo(validar, erros_mod, payloads, horas):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.maquina(horas_maquina=horas))
    assert exc.value.codigo == "INT-008"
    assert exc.value.recuperavel is False


@pytest.mark.parametrize("horas", [0.01, 8.0, 24.0])
def test_regra8_horas_maquina_dentro_do_intervalo(validar, payloads, horas):
    assert validar(payloads.maquina(horas_maquina=horas))


# -- INT-001 / INT-010 / INT-011 ----------------------------------------------


def test_campo_obrigatorio_ausente(validar, erros_mod, payloads):
    payload = payloads.pesagem()
    del payload["talhao_codigo"]
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payload)
    assert exc.value.codigo == "INT-001"


def test_pesagem_sem_equipamento_rejeita(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(equipamento_codigo=None))
    assert exc.value.codigo == "INT-001"


def test_insumo_sem_quantidade_positiva(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.insumo(quantidade=0.0))
    assert exc.value.codigo == "INT-010"


def test_tipo_desconhecido_nao_parseavel(validar, erros_mod, payloads):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(payloads.pesagem(tipo="TRANSFERENCIA"))
    assert exc.value.codigo == "INT-011"


def test_payload_nao_e_objeto(validar, erros_mod):
    with pytest.raises(erros_mod.ErroRejeicao) as exc:
        validar(["não", "sou", "um", "dict"])
    assert exc.value.codigo == "INT-011"
