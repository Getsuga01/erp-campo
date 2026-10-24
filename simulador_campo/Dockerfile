# Simulador do Sistema de Campo (Módulo A) — demo fictícia.
# Construir a partir da RAIZ do repositório (docker build -t simulador-campo .),
# pois o contexto precisa incluir a pasta simulador_campo/.
FROM python:3.12-slim

WORKDIR /app

COPY simulador_campo/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY simulador_campo/ ./

EXPOSE 8001

# Imports top-level absolutos: rodar a partir da pasta do módulo (WORKDIR /app).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
