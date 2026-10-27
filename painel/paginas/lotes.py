"""Página Lotes — histórico com filtros e drill-down por lote (4.7).

A listagem usa V_INDICADORES_LOTE (taxa de sucesso, duração e conferência
de registros vinculados); o drill-down consulta os registros da tabela base
INT_REGISTRO (a view não desce ao nível de registro).
"""
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from componentes.tabelas import exibir_tabela
from config import consultar, para_sao_paulo

_SQL_LOTES = (
    "SELECT lote_id, status, total_recebidos, total_gravados, total_rejeitados, total_duplicados, "
    "       taxa_sucesso_pct, duracao_minutos, iniciado_em, fechado_em, qtd_registros_vinculados "
    "  FROM V_INDICADORES_LOTE "
    " WHERE (:status IS NULL OR status = :status) "
    "   AND (:de IS NULL OR iniciado_em >= :de) "
    "   AND (:ate IS NULL OR iniciado_em < :ate) "
    " ORDER BY lote_id DESC"
)

_SQL_REGISTROS_LOTE = (
    "SELECT id, lote_id, id_origem, tipo, status, codigo_erro, mensagem_erro, "
    "       recebido_em, processado_em, origem "
    "  FROM INT_REGISTRO WHERE lote_id = :lote ORDER BY id"
)


def carregar_lotes(
    status: str | None = None, de: date | None = None, ate: date | None = None
) -> pd.DataFrame:
    """Histórico de lotes via V_INDICADORES_LOTE; `ate` inclusivo na UI (exclusivo no SQL)."""
    filtros = {
        "status": status or None,
        "de": datetime.combine(de, time.min) if de is not None else None,
        "ate": datetime.combine(ate + timedelta(days=1), time.min) if ate is not None else None,
    }
    return pd.DataFrame(consultar(_SQL_LOTES, filtros))


def carregar_registros_lote(lote_id: int) -> pd.DataFrame:
    """Registros vinculados a um lote (drill-down por item, read-only)."""
    return pd.DataFrame(consultar(_SQL_REGISTROS_LOTE, {"lote": lote_id}))


def render() -> None:
    """Renderiza o histórico filtrado e o drill-down do lote escolhido."""
    st.title("Lotes")
    st.caption("histórico dos ciclos de integração — horários em America/Sao_Paulo (banco em UTC).")

    with st.expander("filtros", expanded=True):
        coluna_status, coluna_de, coluna_ate = st.columns(3)
        status = coluna_status.selectbox("status", ["todos", "EM_ANDAMENTO", "CONCLUIDO", "FALHOU"])
        de = coluna_de.date_input("iniciado de (UTC)", value=None)
        ate = coluna_ate.date_input("iniciado até (UTC, inclusivo)", value=None)

    try:
        df = carregar_lotes(
            status=None if status == "todos" else status,
            de=de,
            ate=ate,
        )
    except Exception as erro:
        st.error(f"falha ao consultar o Oracle: {erro}")
        return
    if df.empty:
        st.info("nenhum lote para os filtros atuais")
        return

    df["iniciado_em"] = df["iniciado_em"].map(para_sao_paulo)
    df["fechado_em"] = df["fechado_em"].map(para_sao_paulo)
    exibir_tabela(df, "lotes", "Histórico")

    st.subheader("Drill-down por lote")
    opcoes = {f"lote {int(linha['lote_id'])} — {linha['status']}": int(linha["lote_id"]) for _, linha in df.iterrows()}
    rotulo = st.selectbox("lote", list(opcoes))
    lote_id = opcoes[rotulo]  # o selectbox devolve o RÓTULO — mapeia de volta para o id
    try:
        registros = carregar_registros_lote(lote_id)
    except Exception as erro:
        st.error(f"falha ao consultar o Oracle: {erro}")
        return
    if not registros.empty:
        registros["recebido_em"] = registros["recebido_em"].map(para_sao_paulo)
        registros["processado_em"] = registros["processado_em"].map(para_sao_paulo)
    exibir_tabela(registros, f"registros_lote_{lote_id}", f"Registros do lote {lote_id}")
