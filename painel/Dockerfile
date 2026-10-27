# Painel de Conciliação (Módulo C) — demo fictícia.
# Construir a partir da RAIZ do repositório (docker build -t painel .),
# pois o contexto precisa incluir a pasta painel/.
# As consultas ao Oracle usam python-oracledb em modo THIN — não requer
# oracle instant client na imagem.
FROM python:3.12-slim

WORKDIR /app

COPY painel/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY painel/ ./

EXPOSE 8501

# Imports top-level absolutos: rodar a partir da pasta do módulo (WORKDIR /app).
CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
