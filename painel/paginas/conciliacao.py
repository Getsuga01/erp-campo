"""Página Conciliação — origem × destino por dia e tipo (4.4).

Tabela da V_CONCILIACAO_DIA_TIPO com filtro por período; divergências
são exibidas em VERMELHO (linha inteira) e totalizadas no topo.
"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from componentes.graficos import grafico_linhas
from componentes.tabelas import exibir_tabela
from config import consultar

_SQL = (
    "SELECT dia, tipo, recebidos, gravados, duplicados, rejeitados, pendentes_fila, divergencia "
    "  FROM V_CONCILIACAO_DIA_TIPO "
    " WHERE (:de IS NULL OR dia >= :de) "
    "   AND (:ate IS NULL OR dia < :ate) "
    " ORDER BY dia, tipo"
)

_COLUNAS_SOMA = ["recebidos", "gravados", "duplicados", "rejeitados", "pendentes_fila", "divergencia"]


def carregar_conciliacao(de: date | None = None, ate: date | None = None) -> pd.DataFrame:
    """Conciliação por dia (UTC) × tipo; `ate` é inclusivo na UI (exclusivo no SQL)."""
    filtros = {
        "de": de,
        "ate": ate + timedelta(days=1) if ate is not None else None,
    }
    return pd.DataFrame(consultar(_SQL, filtros))


def render() -> None:
    """Renderiza a tabela origem × destino com filtro de período."""
    st.title("Conciliação — Origem × Destino")
    st.caption("agregação por dia (UTC) × tipo; a equação recebidos = gravados + duplicados + rejeitados + pendentes deve fechar em todas as linhas.")

    coluna_de, coluna_ate = st.columns(2)
    de = coluna_de.date_input("de (dia, UTC)", value=None)
    ate = coluna_ate.date_input("até (dia, UTC, inclusivo)", value=None)
    if de is not None and ate is not None and de > ate:
        st.error("o período é inválido: 'de' é posterior a 'até'")
        return

    try:
        df = carregar_conciliacao(de, ate)
    except Exception as erro:
        st.error(f"falha ao consultar o Oracle: {erro}")
        return
    if df.empty:
        st.info("sem dados para o período")
        return

    totais = {coluna: int(df[coluna].sum()) for coluna in _COLUNAS_SOMA}
    st.success(
        f"{len(df)} combinação(ões) dia×tipo — recebidos {totais['recebidos']}, "
        f"gravados {totais['gravados']}, duplicados {totais['duplicados']}, "
        f"rejeitados {totais['rejeitados']}, pendentes {totais['pendentes_fila']}"
    )
    if totais["divergencia"] != 0:
        st.error(f"⚠️ divergência total do período: {totais['divergencia']} (linhas divergentes em vermelho)")
    else:
        st.info("divergência total do período: 0")

    exibir_tabela(df, "conciliacao", coluna_alerta="divergencia")

    st.subheader("Recebidos × gravados por dia")
    por_dia = (
        df.groupby("dia", as_index=False)[["recebidos", "gravados"]].sum()
        .melt(id_vars=["dia"], value_vars=["recebidos", "gravados"], var_name="métrica", value_name="valor")
    )
    grafico_linhas(por_dia, "dia", "valor", "evolução do período (UTC)", serie="métrica")
