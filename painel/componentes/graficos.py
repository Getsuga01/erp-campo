"""Gráficos do painel via Altair — barras, linhas e pizza (4.9).

O Altair já acompanha o Streamlit (nenhuma dependência extra). Os DataFrames
chegam prontos das páginas; aqui apenas se escolhe a marca e os canais.

Estilo dashboard ERP (tema.py): paleta slate para dados, fundo dos gráficos
branco com borda discreta, títulos pequenos e sobrios. Vermelho/verde NÃO
entrando na paleta da série — ficam reservados para divergência/tendência.
"""
import altair as alt
import pandas as pd
import streamlit as st

from tema import PALETA_SLATE


def _configurar(grafico: alt.Chart, titulo: str) -> alt.Chart:
    """Applya o estilo comum: fundo branco, borda, título sóbrio e paleta slate."""
    return (
        grafico.properties(title=titulo, padding=12)
        .configure_title(fontSize=12, fontWeight=600, color="#37474F", dy=-8)
        .configure_axis(labelColor="#6C757D", titleColor="#6C757D", domainColor="#E9ECEF", gridColor="#F1F3F5")
        .configure_view(fill="#FFFFFF", stroke="#E9ECEF", cornerRadius=8)
        .configure_range(category=alt.RangeScheme(PALETA_SLATE))
    )


def grafico_barras(df: pd.DataFrame, eixo_x: str, eixo_y: str, titulo: str) -> None:
    """Gráfico de barras verticais ordenado pelo eixo y (ex.: contagem por motivo)."""
    if df.empty:
        st.info("sem dados para o gráfico")
        return
    grafico = (
        alt.Chart(df)
        .mark_bar(color="#37474F", cornerRadius=3)
        .encode(
            x=alt.X(eixo_x, sort="-y"),
            y=eixo_y,
            tooltip=[eixo_x, eixo_y],
        )
    )
    st.altair_chart(_configurar(grafico, titulo), width="stretch")


def grafico_linhas(
    df: pd.DataFrame, eixo_x: str, eixo_y: str, titulo: str, serie: str | None = None
) -> None:
    """Gráfico de linhas (ex.: recebidos × gravados por dia); `serie` desenha uma linha por categoria."""
    if df.empty:
        st.info("sem dados para o gráfico")
        return
    canais = {"x": eixo_x, "y": eixo_y, "tooltip": [eixo_x, eixo_y]}
    if serie:
        canais["color"] = serie
        canais["tooltip"].append(serie)
        marcas_kwargs = {"point": True, "size": 65}
    else:
        canais["color"] = alt.value("#546E7A")
        marcas_kwargs = {"point": True, "size": 50}
    grafico = alt.Chart(df).mark_line(**marcas_kwargs).encode(**canais)
    st.altair_chart(_configurar(grafico, titulo), width="stretch")


def grafico_pizza(df: pd.DataFrame, fatia: str, valor: str, titulo: str) -> None:
    """Gráfico de pizza/donut (ex.: distribuição de desfechos dos registros)."""
    if df.empty:
        st.info("sem dados para o gráfico")
        return
    base = alt.Chart(df).encode(
        theta=alt.Theta(valor, type="quantitative"),
        color=alt.Color(fatia, type="nominal"),
        tooltip=[fatia, valor],
    )
    grafico = base.mark_arc(innerRadius=55, outerRadius=120, stroke="#FFFFFF", strokeWidth=2)
    st.altair_chart(_configurar(grafico, titulo), width="stretch")
