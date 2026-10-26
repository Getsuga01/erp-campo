# Serviço de Integração (Módulo B) — demo fictícia.
# Construir a partir da RAIZ do repositório (docker build -t integrador .),
# pois o contexto precisa incluir a pasta integrador/.
# O acesso ao Oracle usa python-oracledb em modo THIN — não requer
# oracle instant client na imagem.
FROM python:3.12-slim

WORKDIR /app

COPY integrador/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY integrador/ ./

EXPOSE 8002

# Imports top-level absolutos: rodar a partir da pasta do módulo (WORKDIR /app).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
