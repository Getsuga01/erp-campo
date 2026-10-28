"""Card de KPI (métrica) dos dashboards do painel (4.9).

Estilo dashboard ERP: cada KPI em um card branco com borda 1px e sombra
sutil sobre o fundo cinza — números grandes no topo, rótulo pequeno
(secundário). O visual do card/vale vem do CSS do tema.py; aqui só a
estrutura do widget.
"""
import streamlit as st


def card(titulo: str, valor, ajuda: str | None = None) -> None:
    """Renderiza um card de métrica (st.metric) com dica opcional."""
    with st.container(border=True):
        st.metric(label=titulo, value=valor, help=ajuda)


def linha_de_cards(itens: list[dict]) -> None:
    """Renderiza uma linha de cards lado a lado.

    Cada item é um dicionário com "titulo" e "valor" (e "ajuda" opcional):
        linha_de_cards([{"titulo": "Recebidos", "valor": 100}, ...])
    """
    colunas = st.columns(len(itens))
    for coluna, item in zip(colunas, itens):
        with coluna:
            card(item["titulo"], item["valor"], item.get("ajuda"))
