"""Card de KPI (métrica) dos dashboards do painel (4.9)."""
import streamlit as st


def card(titulo: str, valor, ajuda: str | None = None) -> None:
    """Renderiza um card de métrica (st.metric) com dica opcional."""
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
