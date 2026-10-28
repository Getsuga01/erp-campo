"""Página Reprocessamento — ação manual via POST /reprocessar do integrador (4.8).

Seleciona itens da fila (PENDENTE/DEAD_LETTER), exige motivo OBRIGATÓRIO
(validado no cliente antes da chamada) e registra quem acionou (default
"PAINEL"). A gravação é feita pelo integrador — o painel não escreve no
banco.
"""
import httpx
import pandas as pd
import streamlit as st

from config import consultar, obter_settings, para_sao_paulo

_SQL_CANDIDATOS = (
    "SELECT f.registro_id, r.id_origem, r.tipo, f.situacao, f.tentativas, f.max_tentativas, "
    "       r.codigo_erro, r.mensagem_erro, f.criado_em "
    "  FROM FILA_REPROCESSAMENTO f JOIN INT_REGISTRO r ON r.id = f.registro_id "
    " WHERE f.situacao IN ('PENDENTE', 'DEAD_LETTER') "
    " ORDER BY f.situacao, f.registro_id"
)


def carregar_candidatos() -> pd.DataFrame:
    """Itens reprocessáveis: fila PENDENTE ou DEAD_LETTER (read-only), com corte de segurança."""
    return pd.DataFrame(consultar(_SQL_CANDIDATOS, limite=obter_settings().limite_listagem))


def acionar_reprocessamento(registro_ids: list[int], motivo: str, acionado_por: str) -> dict:
    """Chama POST /reprocessar do integrador (header X-API-Key) e devolve a resposta."""
    cfg = obter_settings()
    resposta = httpx.post(
        f"{cfg.integrador_url}/reprocessar",
        headers={"X-API-Key": cfg.integrador_api_key},
        json={"registro_ids": registro_ids, "motivo": motivo, "acionado_por": acionado_por},
        timeout=cfg.timeout_http_seg,
    )
    resposta.raise_for_status()
    return resposta.json()


def render() -> None:
    """Renderiza a seleção de itens, o formulário e o resultado da ação."""
    st.title("Reprocessamento Manual")
    st.caption("selecione itens da fila, informe o motivo OBRIGATÓRIO e acione — a execução é feita pelo integrador (POST /reprocessar).")

    try:
        candidatos = carregar_candidatos()
    except Exception as erro:
        st.error(f"falha ao consultar o Oracle: {erro}")
        return
    if candidatos.empty:
        st.info("nenhum item reprocessável (fila sem PENDENTE/DEAD_LETTER)")
        return

    if not candidatos.empty:
        candidatos["criado_em"] = candidatos["criado_em"].map(para_sao_paulo)
    st.dataframe(candidatos, width="stretch", hide_index=True)

    rotulos = {
        f"{int(linha['registro_id'])} | {linha['id_origem']} | {linha['situacao']}": int(linha["registro_id"])
        for _, linha in candidatos.iterrows()
    }
    selecionados = st.multiselect("itens a reprocessar", list(rotulos))
    motivo = st.text_area("motivo (obrigatório)", placeholder="descreva o motivo do reprocessamento")
    acionado_por = st.text_input("acionado por", value="PAINEL")

    if st.button("Reprocessar selecionados", type="primary"):
        if not selecionados:
            st.error("selecione ao menos um item da fila")
            return
        if not motivo.strip():
            st.error("o motivo é obrigatório")
            return
        registro_ids = sorted({rotulos[rotulo] for rotulo in selecionados})
        try:
            resultado = acionar_reprocessamento(registro_ids, motivo.strip(), acionado_por.strip() or "PAINEL")
        except httpx.HTTPStatusError as erro:
            detalhe = erro.response.json().get("detalhe", erro.response.text)
            st.error(f"integrador recusou a chamada (HTTP {erro.response.status_code}): {detalhe}")
            return
        except httpx.HTTPError as erro:
            st.error(f"falha ao chamar o integrador: {erro}")
            return
        st.success(f"{resultado['reprocessados']} de {len(registro_ids)} item(ns) processado(s)")
        st.dataframe(pd.DataFrame(resultado["resultados"]), width="stretch", hide_index=True)
