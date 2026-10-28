"""Tabelas de dados com paginação e exportação CSV (4.9)."""
import pandas as pd
import streamlit as st


def exibir_tabela(
    df: pd.DataFrame,
    chave: str,
    titulo: str | None = None,
    por_pagina: int = 50,
    coluna_alerta: str | None = None,
) -> None:
    """Exibe um DataFrame com paginação e botão de download do CSV completo.

    `chave` diferencia os widgets entre chamadas (mesma página pode ter mais
    de uma tabela). `coluna_alerta`, quando informada, pinta de VERMELHO as
    linhas em que a coluna tenha valor diferente de zero (ex.: divergência
    da conciliação).
    """
    if titulo:
        st.subheader(titulo)
    if df.empty:
        st.info("sem registros para os filtros atuais")
        return

    total_paginas = -(-len(df) // por_pagina)
    pagina = st.selectbox(
        "página",
        range(1, total_paginas + 1),
        format_func=lambda numero: f"{numero} / {total_paginas}",
        key=f"{chave}_pagina",
    )
    inicio = (pagina - 1) * por_pagina
    fatia = df.iloc[inicio : inicio + por_pagina].reset_index(drop=True)

    if coluna_alerta and coluna_alerta in fatia.columns:
        fatia = _com_realce_vermelho(fatia, coluna_alerta)
    st.dataframe(fatia, width="stretch", hide_index=True)

    st.download_button(
        "baixar CSV (base completa)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"{chave}.csv",
        mime="text/csv",
        key=f"{chave}_csv",
    )


def _com_realce_vermelho(df: pd.DataFrame, coluna_alerta: str):
    """Devolve um Styler com a linha inteira em vermelho quando a coluna de alerta != 0."""

    def _pintar(linha) -> list[str]:
        return ["color: #d32f2f"] * len(linha) if linha[coluna_alerta] != 0 else [""] * len(linha)

    return df.style.apply(_pintar, axis=1)
