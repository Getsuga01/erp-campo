"""Testes do cursor incremental seguro (tarefa 5.4) — regra 2 do plano.

O cursor só avança DEPOIS que o lote inteiro foi persistido. Um crash no
meio do processamento fecha o lote como FALHOU e mantém o cursor — o
próximo ciclo repega tudo; a idempotência transforma os já gravados em
duplicados, sem efeitos duplicados no ERP (cursor.py, ciclo.py).
"""
import pytest

from conftest import CURSOR_FINAL_PADRAO, SENTINELA, NOME_CURSOR, rodar_ciclo


def test_crash_no_meio_do_lote_nao_avanca_cursor(int_mod, oracle, monkeypatch, payloads):
    itens = [payloads.pesagem(), payloads.maquina(), payloads.insumo()]
    oracle.falhar_apontamento_em = 2  # crash no INSERT do 2º apontamento

    resultado = rodar_ciclo(int_mod, monkeypatch, itens)

    assert resultado["status"] == "FALHOU"
    assert resultado["codigo_erro"] == "INT-052"
    # Cursor NÃO avançou: continua na sentinela semeada no início do ciclo
    assert oracle.cursors[NOME_CURSOR] == SENTINELA
    # Commit POR REGISTRO: o 1º registro sobreviveu; o 2º foi revertido
    assert len(oracle.registros) == 1
    assert oracle.registros[0].status == "GRAVADO"
    assert len(oracle.apontamentos) == 1
    # O lote existe e foi fechado como FALHOU com o código no observacao
    lote = next(l for l in oracle.lotes if l.id == resultado["lote_id"])
    assert lote.status == "FALHOU"
    assert lote.observacao.startswith("INT-052")


def test_proximo_ciclo_repega_registros_e_contabiliza_duplicados(
    int_mod, oracle, monkeypatch, payloads
):
    itens = [payloads.pesagem(), payloads.maquina(), payloads.insumo()]
    oracle.falhar_apontamento_em = 2
    rodar_ciclo(int_mod, monkeypatch, itens)  # crash no 2º registro

    oracle.falhar_apontamento_em = None  # infraestrutura restabelecida
    resultado = rodar_ciclo(int_mod, monkeypatch, itens, cursor_final=CURSOR_FINAL_PADRAO)

    assert resultado["status"] == "CONCLUIDO"
    # 1 já gravado no ciclo falho → duplicado; 2 novos → gravados
    assert (resultado["gravados"], resultado["rejeitados"], resultado["duplicados"]) == (2, 0, 1)
    assert resultado["recebidos"] == 3
    # Efeitos finais no ERP: exatamente 3 apontamentos, nada duplicado
    assert len(oracle.apontamentos) == 3
    assert len(oracle.registros) == 3
    # Agora sim o cursor avançou
    assert oracle.cursors[NOME_CURSOR] == CURSOR_FINAL_PADRAO


def test_sem_dados_nao_cria_lote_nem_avanca_cursor(int_mod, oracle, monkeypatch, payloads):
    rodar_ciclo(int_mod, monkeypatch, [])  # origem sem novidades
    assert oracle.lotes == []
    assert oracle.cursors == {NOME_CURSOR: SENTINELA}  # apenas o seed do ler_cursor


def test_ler_cursor_semeia_sentinela_quando_ausente(int_mod, oracle):
    cursor_mod = int_mod("cursor")
    assert oracle.cursors == {}
    assert cursor_mod.ler_cursor() == SENTINELA
    assert oracle.cursors[NOME_CURSOR] == SENTINELA


def test_avancar_cursor_sem_linha_levanta_erro(int_mod, oracle):
    cursor_mod = int_mod("cursor")
    with pytest.raises(RuntimeError, match="não encontrado para avançar"):
        cursor_mod.avancar_cursor("2026-10-26T14:00:00Z")


def test_avancar_cursor_e_atomico(int_mod, oracle):
    cursor_mod = int_mod("cursor")
    cursor_mod.ler_cursor()  # semeia a linha
    cursor_mod.avancar_cursor("2026-10-26T14:00:00Z")
    assert oracle.cursors[NOME_CURSOR] == "2026-10-26T14:00:00Z"
