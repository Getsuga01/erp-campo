"""Gráficos do painel via Altair — barras, linhas e pizza (4.9).

O Altair já acompanha o Streamlit (nenhuma dependência extra). Os DataFrames
chegam prontos das páginas; aqui apenas se escolhe a marca e os canais.
"""
import altair as alt
import pandas as pd
import streamlit as st


def grafico_barras(df: pd.DataFrame, eixo_x: str, eixo_y: str, titulo: str) -> None:
    """Gráfico de barras verticais ordenado pelo eixo y (ex.: contagem por motivo)."""
    if df.empty:
        st.info("sem dados para o gráfico")
        return
    grafico = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(eixo_x, sort="-y"),
            y=eixo_y,
            tooltip=[eixo_x, eixo_y],
        )
        .properties(title=titulo)
    )
    st.altair_chart(grafico, use_container_width=True)


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
    grafico = alt.Chart(df).mark_line(point=True).encode(**canais).properties(title=titulo)
    st.altair_chart(grafico, use_container_width=True)


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
    grafico = base.mark_arc(innerRadius=50, outerRadius=120, stroke="#fff").properties(title=titulo)
    st.altair_chart(grafico, use_container_width=True)
