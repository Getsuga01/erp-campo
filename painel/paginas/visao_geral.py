"""Página Visão Geral — indicadores do pipeline Campo → ERP (4.3).

Cards obrigatórios: recebidos, gravados, rejeitados, duplicados, pendentes,
taxa de sucesso na 1ª tentativa, top 5 motivos de rejeição, tempo médio/p95
por lote, idade da fila e divergência da equação
recebidos = gravados + duplicados + rejeitados + pendentes (≠ 0 em destaque).
"""
import math

import pandas as pd
import streamlit as st

from componentes.graficos import grafico_barras, grafico_linhas, grafico_pizza
from componentes.metricas_card import linha_de_cards
from componentes.tabelas import exibir_tabela
from config import consultar, para_sao_paulo

_SQL_TOTAIS = (
    "SELECT NVL(SUM(recebidos), 0)      AS recebidos, "
    "       NVL(SUM(gravados), 0)      AS gravados, "
    "       NVL(SUM(duplicados), 0)     AS duplicados, "
    "       NVL(SUM(rejeitados), 0)     AS rejeitados, "
    "       NVL(SUM(pendentes_fila), 0) AS pendentes, "
    "       NVL(SUM(divergencia), 0)    AS divergencia "
    "  FROM V_CONCILIACAO_DIA_TIPO"
)

# Gravados na 1ª tentativa: desfecho GRAVADO sem NUNCA ter passado pela fila.
_SQL_TAXA_PRIMEIRA = (
    "SELECT COUNT(*) AS recebidos, "
    "       NVL(SUM(CASE WHEN r.status = 'GRAVADO' AND f.registro_id IS NULL "
    "                    THEN 1 ELSE 0 END), 0) AS gravados_primeira "
    "  FROM INT_REGISTRO r "
    "  LEFT JOIN (SELECT DISTINCT registro_id FROM FILA_REPROCESSAMENTO) f "
    "    ON f.registro_id = r.id"
)

_SQL_TOP_ERROS = (
    "SELECT codigo_erro, qtd, ultima_ocorrencia "
    "  FROM (SELECT * FROM V_TOP_ERROS ORDER BY qtd DESC, codigo_erro) "
    " WHERE ROWNUM <= :limite"
)

# Mensagem da ocorrência mais recente de cada código (V_TOP_ERROS não traz texto).
_SQL_MENSAGEM_ERRO = (
    "SELECT mensagem_erro "
    "  FROM (SELECT mensagem_erro FROM INT_REGISTRO "
    "         WHERE codigo_erro = :codigo AND mensagem_erro IS NOT NULL "
    "         ORDER BY id DESC) "
    " WHERE ROWNUM = 1"
)

_SQL_DURACOES = (
    "SELECT duracao_minutos FROM V_INDICADORES_LOTE "
    " WHERE duracao_minutos IS NOT NULL ORDER BY duracao_minutos"
)

_SQL_FILA = "SELECT situacao, qtd, idade_mais_antigo_min FROM V_FILA_STATUS ORDER BY situacao"

_SQL_DIVERGENCIAS = (
    "SELECT dia, tipo, recebidos, gravados, duplicados, rejeitados, pendentes_fila, divergencia "
    "  FROM V_DIVERGENCIAS ORDER BY dia, tipo"
)

_SQL_POR_DIA = (
    "SELECT dia, SUM(recebidos) AS recebidos, SUM(gravados) AS gravados "
    "  FROM V_CONCILIACAO_DIA_TIPO GROUP BY dia ORDER BY dia"
)


def carregar_totais() -> dict:
    """Somas globais da conciliação (V_CONCILIACAO_DIA_TIPO)."""
    return consultar(_SQL_TOTAIS)[0]


def carregar_taxa_primeira_tentativa() -> float | None:
    """% de registros gravados sem nunca passar pela fila (sucesso na 1ª tentativa)."""
    linha = consultar(_SQL_TAXA_PRIMEIRA)[0]
    recebidos, gravados_primeira = int(linha["recebidos"]), int(linha["gravados_primeira"])
    if recebidos == 0:
        return None
    return round(gravados_primeira * 100 / recebidos, 2)


def carregar_top_erros(limite: int = 5) -> list[dict]:
    """Top N motivos de rejeição por quantidade, com a mensagem da última ocorrência."""
    itens = consultar(_SQL_TOP_ERROS, {"limite": limite})
    for item in itens:
        mensagem = consultar(_SQL_MENSAGEM_ERRO, {"codigo": item["codigo_erro"]})
        item["mensagem"] = mensagem[0]["mensagem_erro"] if mensagem else None
        item["ultima_ocorrencia_local"] = para_sao_paulo(item["ultima_ocorrencia"])
    return itens


def carregar_duracoes_lotes() -> list[float]:
    """Durações (minutos) de todos os lotes fechados (V_INDICADORES_LOTE), ordenadas."""
    return [float(linha["duracao_minutos"]) for linha in consultar(_SQL_DURACOES)]


def carregar_fila_status() -> list[dict]:
    """Quantidade e idade do item mais antigo por situação da fila (V_FILA_STATUS)."""
    return consultar(_SQL_FILA)


def carregar_divergencias() -> list[dict]:
    """Dias/tipos em que a equação da conciliação NÃO fecha (V_DIVERGENCIAS)."""
    return consultar(_SQL_DIVERGENCIAS)


def carregar_por_dia() -> pd.DataFrame:
    """Recebidos e gravados agregados por dia (para o gráfico de linhas)."""
    df = pd.DataFrame(consultar(_SQL_POR_DIA))
    if not df.empty:
        df = df.melt(id_vars=["dia"], value_vars=["recebidos", "gravados"],
                     var_name="métrica", value_name="valor")
    return df


def render() -> None:
    """Renderiza o dashboard principal."""
    st.title("Visão Geral")
    st.caption("Indicadores da integração Campo → ERP — horários exibidos em America/Sao_Paulo (banco em UTC).")

    try:
        totais = carregar_totais()
        taxa_primeira = carregar_taxa_primeira_tentativa()
        top_erros = carregar_top_erros()
        duracoes = carregar_duracoes_lotes()
        fila_status = carregar_fila_status()
        divergencias = carregar_divergencias()
        por_dia = carregar_por_dia()
    except Exception as erro:
        st.error(f"falha ao consultar o Oracle: {erro}")
        return

    tempo_medio = round(sum(duracoes) / len(duracoes), 3) if duracoes else None
    tempo_p95 = round(duracoes[max(0, math.ceil(0.95 * len(duracoes)) - 1)], 3) if duracoes else None
    pendente = next((item for item in fila_status if item["situacao"] == "PENDENTE"), None)
    idade_fila = f"{int(pendente['idade_mais_antigo_min'])} min" if pendente else "—"

    linha_de_cards(
        [
            {"titulo": "Recebidos", "valor": int(totais["recebidos"])},
            {"titulo": "Gravados", "valor": int(totais["gravados"])},
            {"titulo": "Rejeitados (definitivos)", "valor": int(totais["rejeitados"])},
            {"titulo": "Duplicados", "valor": int(totais["duplicados"])},
            {"titulo": "Pendentes", "valor": int(totais["pendentes"])},
        ]
    )
    linha_de_cards(
        [
            {"titulo": "Taxa de sucesso 1ª tentativa", "valor": f"{taxa_primeira}%" if taxa_primeira is not None else "—",
             "ajuda": "registros gravados que nunca passaram pela fila de reprocessamento ÷ recebidos"},
            {"titulo": "Tempo médio por lote", "valor": f"{tempo_medio} min" if tempo_medio is not None else "—"},
            {"titulo": "Tempo p95 por lote", "valor": f"{tempo_p95} min" if tempo_p95 is not None else "—"},
            {"titulo": "Idade da fila (mais antigo)", "valor": idade_fila,
             "ajuda": "idade do item PENDENTE mais antigo da fila de reprocessamento"},
            {"titulo": "Divergência (equação)", "valor": int(totais["divergencia"]),
             "ajuda": "recebidos − gravados − duplicados − rejeitados − pendentes; esperado 0"},
        ]
    )

    if int(totais["divergencia"]) != 0:
        st.error("⚠️ a equação recebidos = gravados + duplicados + rejeitados + pendentes NÃO fecha — verifique:")
        exibir_tabela(pd.DataFrame(divergencias), "divergencias", coluna_alerta="divergencia")
    else:
        st.success("equação da conciliação fechada (divergência = 0)")

    coluna_erros, coluna_pizza = st.columns(2)
    with coluna_erros:
        st.subheader("Top 5 motivos de rejeição")
        if top_erros:
            df_erros = pd.DataFrame(
                [
                    {
                        "código": item["codigo_erro"],
                        "qtd": int(item["qtd"]),
                        "mensagem": item["mensagem"],
                        "última ocorrência": item["ultima_ocorrencia_local"],
                    }
                    for item in top_erros
                ]
            )
            grafico_barras(df_erros, "código", "qtd", "rejeições por motivo")
            st.dataframe(df_erros, use_container_width=True, hide_index=True)
        else:
            st.info("nenhuma rejeição registrada")
    with coluna_pizza:
        st.subheader("Desfechos dos registros")
        df_desfechos = pd.DataFrame(
            [
                {"desfecho": "gravados", "qtd": int(totais["gravados"])},
                {"desfecho": "duplicados", "qtd": int(totais["duplicados"])},
                {"desfecho": "rejeitados", "qtd": int(totais["rejeitados"])},
                {"desfecho": "pendentes", "qtd": int(totais["pendentes"])},
            ]
        )
        grafico_pizza(df_desfechos, "desfecho", "qtd", "distribuição dos desfechos")

    st.subheader("Recebidos × gravados por dia")
    grafico_linhas(por_dia, "dia", "valor", "evolução diária (UTC)", serie="métrica")
