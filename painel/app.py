"""Painel de Conciliação (Módulo C) — Streamlit multi-page na porta 8501.

Demo fictícia: monitora a integração Campo → ERP a partir das views do
Oracle (read-only) e aciona o reprocessamento manual via POST /reprocessar
do integrador (porta 8002).

Como rodar (imports top-level absolutos — igual aos outros módulos):
    streamlit run painel/app.py --server.headless true --server.port 8501

Navegação (4.1): as páginas vivem no pacote próprio painel/paginas/
(NÃO na convenção nativa pages/ do Streamlit, que conflita com paginas/);
o app.py monta a navegação com st.navigation/st.Page importando cada página.
"""
import sys
import time
from pathlib import Path

# Garante que paginas/ e componentes/ sejam importáveis independente do
# diretório a partir do qual o streamlit foi disparado.
_PASTA_PAINEL = Path(__file__).resolve().parent
if str(_PASTA_PAINEL) not in sys.path:
    sys.path.insert(0, str(_PASTA_PAINEL))

import streamlit as st

from config import obter_settings
from paginas import conciliacao, fila, lotes, rejeicoes, reprocessamento, visao_geral
from tema import aplicar_tema

st.set_page_config(
    page_title="Painel de Conciliação — Campo → ERP",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tema visual "dashboard ERP" (SAP Fiori/Odoo style): fundo cinza, cards brancos
# com borda 1px, paleta slate, tipografia Inter tabular — ver tema.py.
aplicar_tema()

st.sidebar.title("🌾 Campo → ERP")
st.sidebar.caption("painel de conciliação da integração — horários em America/Sao_Paulo (banco em UTC)")

pg = st.navigation(
    [
        st.Page(visao_geral.render, title="Visão Geral", icon="📊", url_path="visao_geral", default=True),
        st.Page(conciliacao.render, title="Conciliação", icon="⚖️", url_path="conciliacao"),
        st.Page(rejeicoes.render, title="Rejeições", icon="🚫", url_path="rejeicoes"),
        st.Page(fila.render, title="Fila", icon="📥", url_path="fila"),
        st.Page(lotes.render, title="Lotes", icon="📦", url_path="lotes"),
        st.Page(reprocessamento.render, title="Reprocessamento", icon="♻️", url_path="reprocessamento"),
    ]
)

# Auto-refresh configurável (PAINEL_AUTO_REFRESH_SEG): 0 = desligado; >0 =
# espera N segundos APÓS renderizar e reroda o app (equivalente nativo do
# st_autorefresh, sem dependência extra).
cfg = obter_settings()
if cfg.auto_refresh_seg > 0:
    st.sidebar.info(f"auto-refresh a cada {cfg.auto_refresh_seg}s (desligue com PAINEL_AUTO_REFRESH_SEG=0)")

pg.run()

if cfg.auto_refresh_seg > 0:
    time.sleep(cfg.auto_refresh_seg)
    st.rerun()
