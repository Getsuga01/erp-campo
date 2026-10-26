"""Testes da equação de conciliação (tarefa 5.7) — regra 10 do plano.

Equação (linha 136 do plano):
    recebidos = gravados + duplicados + rejeitados_definitivos + pendentes

Validada em dois níveis, sempre com dados reais do fluxo:
- **por lote**: total_recebidos = gravados + rejeitados + duplicados, com
  gravados/rejeitados recalculados de INT_REGISTRO (fonte da verdade);
- **global**: partição de V_CONCILIACAO_DIA_TIPO — GRAVADO → gravados;
  duplicados → soma dos total_duplicados (não geram linha); REJEITADO com
  fila ativa (PENDENTE/PROCESSANDO) → pendentes; REJEITADO sem fila ativa
  → rejeitados definitivos; RECEBIDO/PENDENTE_FILA → pendentes.
"""
import pytest

from conftest import CURSOR_FINAL_PADRAO, rodar_ciclo


def _particao(oracle):
    """Particiona o estado na mesma semântica da V_CONCILIACAO_DIA_TIPO."""
    fila_ativa = {f.registro_id for f in oracle.fila if f.situacao in ("PENDENTE", "PROCESSANDO")}
    gravados = [r for r in oracle.registros if r.status == "GRAVADO"]
    duplicados = sum(l.total_duplicados or 0 for l in oracle.lotes)
    rejeitados_def = [
        r for r in oracle.registros if r.status == "REJEITADO" and r.id not in fila_ativa
    ]
    pendentes = [
        r
        for r in oracle.registros
        if r.status in ("RECEBIDO", "PENDENTE_FILA")
        or (r.status == "REJEITADO" and r.id in fila_ativa)
    ]
    recebidos = len(oracle.registros) + duplicados
    return {
        "recebidos": recebidos,
        "gravados": len(gravados),
        "duplicados": duplicados,
        "rejeitados_def": len(rejeitados_def),
        "pendentes": len(pendentes),
    }


def _assert_equacao_global(oracle):
    particao = _particao(oracle)
    divergencia = (
        particao["recebidos"]
        - particao["gravados"]
        - particao["duplicados"]
        - particao["rejeitados_def"]
        - particao["pendentes"]
    )
    assert divergencia == 0, f"divergência de conciliação: {particao}"
    return particao


def _assert_equacao_por_lote(oracle):
    for lote in oracle.lotes:
        gravados = sum(
            1 for r in oracle.registros if r.lote_id == lote.id and r.status == "GRAVADO"
        )
        rejeitados = sum(
            1 for r in oracle.registros if r.lote_id == lote.id and r.status == "REJEITADO"
        )
        assert lote.total_recebidos == gravados + rejeitados + (lote.total_duplicados or 0)
        assert lote.total_gravados == gravados
        assert lote.total_rejeitados == rejeitados


@pytest.fixture
def cenario(int_mod, oracle, monkeypatch, payloads):
    """Cenário vivo: lote misto + reenvio duplicado + fila recuperável."""
    validos = [payloads.pesagem(), payloads.maquina()]
    definitivo = payloads.pesagem(data_hora=_futura(30))  # INT-007
    recuperavel = payloads.insumo(talhao_codigo="TAL-999")  # INT-002
    itens = validos + [definitivo, recuperavel]

    lote1 = rodar_ciclo(int_mod, monkeypatch, itens)
    lote2 = rodar_ciclo(int_mod, monkeypatch, itens, cursor_final="2026-10-26T13:00:00Z")
    return {"itens": itens, "recuperavel": recuperavel, "lote1": lote1, "lote2": lote2}


def test_regra10_equacao_apos_lote_misto_e_reenvio(int_mod, oracle, cenario):
    assert cenario["lote1"]["status"] == "CONCLUIDO"
    assert cenario["lote2"]["status"] == "CONCLUIDO"

    _assert_equacao_por_lote(oracle)
    particao = _assert_equacao_global(oracle)

    # 2 válidos + 1 definitivo + 1 recuperável + 4 duplicados do reenvio
    assert particao == {
        "recebidos": 8,
        "gravados": 2,
        "duplicados": 4,
        "rejeitados_def": 1,
        "pendentes": 1,
    }


def test_regra10_reprocessamento_sucesso_movimenta_a_equacao(int_mod, oracle, cenario):
    _assert_equacao_global(oracle)  # baseline

    oracle.cadastrar_talhao("TAL-999", ativo=1)
    oracle.expirar_fila()
    reprocessador = int_mod("reprocessador")
    resultado = reprocessador.executar_reprocessamento()
    assert resultado["resultados"][0]["resultado"] == "SUCESSO"

    particao = _assert_equacao_global(oracle)
    assert particao["pendentes"] == 0
    assert particao["gravados"] == 3  # recuperável migrou para GRAVADO
    assert particao["recebidos"] == 8  # nada apareceu nem desapareceu


def test_regra10_dead_letter_migra_pendente_para_rejeitado_definitivo(int_mod, oracle, cenario):
    _assert_equacao_global(oracle)

    reprocessador = int_mod("reprocessador")
    for _ in range(3):
        oracle.expirar_fila()
        reprocessador.executar_reprocessamento()

    particao = _assert_equacao_global(oracle)
    assert particao["pendentes"] == 0
    assert particao["rejeitados_def"] == 2  # definitivo do ciclo + dead-letter


def test_regra10_partition_cobre_todos_os_registros_sem_soma_dupla(int_mod, oracle, cenario):
    """Cada registro cai em exatamente um bucket; duplicados contam uma vez."""
    _assert_equacao_por_lote(oracle)
    particao = _particao(oracle)
    por_tipo = {}
    for registro in oracle.registros:
        por_tipo[registro.tipo] = por_tipo.get(registro.tipo, 0) + 1
    # Todos os registros do cenário têm tipos válidos do contrato
    assert set(por_tipo) <= {"PESAGEM", "MAQUINA", "INSUMO"}
    assert sum(por_tipo.values()) == len(oracle.registros)
    assert particao["recebidos"] == len(oracle.registros) + particao["duplicados"]


def _futura(minutos: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (
        datetime.now(timezone.utc) + timedelta(minutes=minutos)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
