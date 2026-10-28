"""Tema visual do painel — dashboards ERP validados no mercado (SAP Fiori, Odoo, Power BI admin).

Princípios aplicados (guia dashboard-design):
* fundo cinza claro (#F8F9FA) — os cards brancos se destacam com borda 1px e sombra sutil;
* hierarquia de dados: KPIs grandes no topo, gráficos ao meio, tabelas embaixo;
* paleta mínima: slate para dados; VERDE/VERMELHO reservados para tendência/divergência;
* tipografia tabular (Inter) — números alinhados e comparáveis;
* layout ERP: sidebar branca à esquerda separada por borda + área principal espaçosa.
"""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --fundo: #F8F9FA;
  --card: #FFFFFF;
  --borda: #E9ECEF;
  --texto: #212529;
  --texto-secundario: #6C757D;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
  background-color: var(--fundo);
  color: var(--texto);
  font-family: 'Inter', 'Segoe UI', sans-serif;
}

/* ---- Sidebar (navegação ERP) ---- */
[data-testid="stSidebar"] {
  background-color: var(--card);
  border-right: 1px solid var(--borda);
}
[data-testid="stSidebar"] .stMarkdown h1 {
  font-size: 1.05rem;
  letter-spacing: -0.01em;
  margin-bottom: 0.25rem;
}
[data-testid="stSidebar"] * {
  color: var(--texto);
}

/* ---- Títulos: enxutos, hierarquia clara ---- */
h1, h2, h3 { letter-spacing: -0.01em; font-weight: 700; }
[data-testid="stCaptionContainer"] p { color: var(--texto-secundario); }

/* ---- Cards de KPI (centro do dashboard) ---- */
[data-testid="stMetric"] {
  background: var(--card);
  border: 1px solid var(--borda);
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.03);
}
[data-testid="stMetricLabel"] p {
  color: var(--texto-secundario);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}
[data-testid="stMetricValue"] {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* ---- Cards de conteúdo: tabelas e filtros ---- */
[data-testid="stDataFrame"] {
  border: 1px solid var(--borda);
  border-radius: 10px;
  background: var(--card);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
  overflow: hidden;
}
[data-testid="stExpander"] details {
  border: 1px solid var(--borda);
  border-radius: 10px;
  background: var(--card);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
}

/* ---- Botões: sobriedade ERP (slate) ---- */
.stButton > button, .stDownloadButton > button {
  border: 1px solid var(--borda);
  border-radius: 8px;
  font-weight: 600;
}

/* ---- Inputs com contorno discreto ---- */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {
  border-radius: 8px;
}
</style>
"""


def aplicar_tema() -> None:
    """Injeta o CSS do tema (chamar logo após st.set_page_config)."""
    st.markdown(_CSS, unsafe_allow_html=True)


# Paleta de dados (Minimalist Slate) — usada pelos gráficos Altair do painel.
# Vermelho/verde ficam reservados para divergência/tendência (não entram aqui).
PALETA_SLATE = ["#37474F", "#546E7A", "#78909C", "#90A4AE", "#B0BEC5", "#CFD8DC"]
