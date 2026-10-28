"""Página Fila — estado da fila de reprocessamento e dead-letter (4.6).

Resumo por situação via V_FILA_STATUS (quantidade e idade do item mais
antigo) + listagem dos itens PENDENTES e em DEAD_LETTER (tabela base
FILA_REPROCESSAMENTO, read-only).
"""
import pandas as pd
import streamlit as st

from componentes.tabelas import exibir_tabela
from config import consultar, obter_settings, para_sao_paulo

_SQL_STATUS = "SELECT situacao, qtd, idade_mais_antigo_min FROM V_FILA_STATUS ORDER BY situacao"

_SQL_ITENS = (
    "SELECT f.id, f.registro_id, r.id_origem, r.tipo, f.situacao, f.tentativas, f.max_tentativas, "
    "       f.proxima_tentativa, f.motivo, r.codigo_erro, r.mensagem_erro, f.criado_em, f.atualizado_em "
    "  FROM FILA_REPROCESSAMENTO f JOIN INT_REGISTRO r ON r.id = f.registro_id "
    " ORDER BY f.id"
)


def carregar_status_fila() -> list[dict]:
    """Quantidade e idade do item mais antigo por situação (V_FILA_STATUS)."""
    return consultar(_SQL_STATUS)


def carregar_itens_fila() -> pd.DataFrame:
    """Itens da fila com dados do registro vinculado (read-only), com corte de segurança."""
    return pd.DataFrame(consultar(_SQL_ITENS, limite=obter_settings().limite_listagem))


def render() -> None:
    """Renderiza o estado da fila e as listas de pendentes/dead-letter."""
    st.title("Fila de Reprocessamento")
    st.caption("itens rejeitados recuperáveis aguardando nova tentativa — horários em America/Sao_Paulo (banco em UTC).")

    try:
        status = carregar_status_fila()
        itens = carregar_itens_fila()
    except Exception as erro:
        st.error(f"falha ao consultar o Oracle: {erro}")
        return

    if status:
        colunas = st.columns(len(status))
        for coluna, item in zip(colunas, status):
            with coluna:
                st.metric(
                    label=item["situacao"],
                    value=int(item["qtd"]),
                    help=f"idade do item mais antigo: {int(item['idade_mais_antigo_min'])} min",
                )
    else:
        st.info("fila vazia — nenhum item pendente de reprocessamento")
        return

    if not itens.empty:
        itens["criado_em"] = itens["criado_em"].map(para_sao_paulo)
        itens["atualizado_em"] = itens["atualizado_em"].map(para_sao_paulo)
        itens["proxima_tentativa"] = itens["proxima_tentativa"].map(para_sao_paulo)

    exibir_tabela(itens[itens["situacao"] == "PENDENTE"], "fila_pendente", "Pendentes")
    exibir_tabela(itens[itens["situacao"] == "DEAD_LETTER"], "fila_dead_letter", "Dead-letter")
    exibir_tabela(
        itens[itens["situacao"].isin(["PROCESSANDO", "CONCLUIDA"])],
        "fila_demais",
        "Processando / concluídos",
    )
