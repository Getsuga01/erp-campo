"""Página Rejeições — lista por motivo com filtros e exportação CSV (4.5).

Filtros: lote, tipo, talhão (quando aplicável — lido do payload original) e
período. O resumo por motivo usa a lista filtrada; a tabela detalhada mostra
a situação da fila (recuperável/dead-letter) de cada rejeição.
"""
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from componentes.graficos import grafico_barras
from componentes.tabelas import exibir_tabela
from config import consultar, obter_settings, para_sao_paulo

# Base INT_REGISTRO (a view V_TOP_ERROS não aceita filtros por lote/tipo/período
# nem expõe payload/talhão) — leitura read-only.
_SQL = (
    "SELECT r.id, r.lote_id, r.id_origem, r.tipo, r.codigo_erro, r.mensagem_erro, "
    "       JSON_VALUE(r.payload_original, '$.talhao_codigo') AS talhao_codigo, "
    "       f.situacao AS situacao_fila, f.tentativas, f.max_tentativas, "
    "       r.recebido_em, r.processado_em "
    "  FROM INT_REGISTRO r "
    "  LEFT JOIN (SELECT registro_id, MAX(situacao) AS situacao, MAX(tentativas) AS tentativas, "
    "                    MAX(max_tentativas) AS max_tentativas "
    "               FROM FILA_REPROCESSAMENTO GROUP BY registro_id) f "
    "    ON f.registro_id = r.id "
    " WHERE r.status = 'REJEITADO' "
    "   AND (:lote IS NULL OR r.lote_id = :lote) "
    "   AND (:tipo IS NULL OR r.tipo = :tipo) "
    "   AND (:talhao IS NULL OR JSON_VALUE(r.payload_original, '$.talhao_codigo') = :talhao) "
    "   AND (:de IS NULL OR r.recebido_em >= :de) "
    "   AND (:ate IS NULL OR r.recebido_em < :ate) "
    " ORDER BY r.id DESC"
)


def carregar_rejeicoes(
    lote: int | None = None,
    tipo: str | None = None,
    talhao: str | None = None,
    de: date | None = None,
    ate: date | None = None,
) -> pd.DataFrame:
    """Rejeições com filtros; `ate` é inclusivo na UI (exclusivo no SQL, limites UTC)."""
    filtros = {
        "lote": lote if lote else None,
        "tipo": tipo or None,
        "talhao": talhao or None,
        "de": datetime.combine(de, time.min) if de is not None else None,
        "ate": datetime.combine(ate + timedelta(days=1), time.min) if ate is not None else None,
    }
    return pd.DataFrame(consultar(_SQL, filtros, limite=obter_settings().limite_listagem))


def render() -> None:
    """Renderiza resumo por motivo + tabela detalhada com export CSV."""
    st.title("Rejeições")
    st.caption("registros com status REJEITADO — o motivo (código INT-0xx) vem do catálogo do integrador, gravado no Oracle.")

    with st.expander("filtros", expanded=True):
        coluna_lote, coluna_tipo, coluna_talhao = st.columns(3)
        lote = coluna_lote.number_input("lote (id; 0 = todos)", min_value=0, value=0, step=1)
        tipo = coluna_tipo.selectbox("tipo", ["todos", "PESAGEM", "MAQUINA", "INSUMO"])
        talhao = coluna_talhao.text_input("talhão (código, quando aplicável)")
        coluna_de, coluna_ate = st.columns(2)
        de = coluna_de.date_input("recebido de (UTC)", value=None)
        ate = coluna_ate.date_input("recebido até (UTC, inclusivo)", value=None)

    try:
        df = carregar_rejeicoes(
            lote=int(lote),
            tipo=None if tipo == "todos" else tipo,
            talhao=talhao or None,
            de=de,
            ate=ate,
        )
    except Exception as erro:
        st.error(f"falha ao consultar o Oracle: {erro}")
        return
    if df.empty:
        st.info("nenhuma rejeição para os filtros atuais")
        return

    if not df.empty:
        df["recebido_em"] = df["recebido_em"].map(para_sao_paulo)
        df["processado_em"] = df["processado_em"].map(para_sao_paulo)

    st.subheader("Resumo por motivo")
    resumo = (
        df.groupby("codigo_erro", as_index=False)
        .agg(qtd=("id", "count"), mensagem=("mensagem_erro", "first"))
        .sort_values("qtd", ascending=False)
    )
    grafico_barras(resumo, "codigo_erro", "qtd", "rejeições por motivo (filtro atual)")
    st.dataframe(resumo, width="stretch", hide_index=True)

    exibir_tabela(df, "rejeicoes", "Detalhes")
