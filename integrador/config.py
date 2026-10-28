"""Configuração do integrador via variáveis de ambiente (prefixo INT_)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings lidas do ambiente: INT_ORACLE_DSN, INT_CAMPO_URL, INT_API_KEY etc."""

    model_config = SettingsConfigDict(env_prefix="INT_", extra="ignore")

    # Conexão Oracle (python-oracledb em modo THIN — sem instant client).
    oracle_dsn: str = "localhost:1521/XEPDB1"
    oracle_usuario: str = "INTEGRACAO"
    # Senha fictícia da demo local, idêntica a db/01_schema.sql; em produção,
    # definir a env INT_ORACLE_SENHA. NUNCA logar este valor.
    oracle_senha: str = "IntegracaoFicticia2026"

    # Origem dos apontamentos (Módulo A — simulador do sistema de campo).
    campo_url: str = "http://localhost:8001"
    campo_api_key: str = "campo-dev-key-001"

    # Chave exigida no header X-API-Key da API administrativa (exceto /health).
    api_key: str = "integrador-dev-key-001"

    # Intervalos dos jobs agendados (em minutos).
    ciclo_intervalo_min: int = 5
    reproc_intervalo_min: int = 2

    # Fila de reprocessamento.
    max_tentativas: int = 3

    # Regras de validação.
    peso_limite_alerta: float = 60000
    tolerancia_futuro_min: int = 5

    # Serviço (a porta efetiva é definida ao subir o uvicorn; o Dockerfile fixa 8002).
    porta: int = 8002
    timeout_http_seg: int = 10
    limite_pagina: int = 100

    # Pool de conexões Oracle (min/max) — pool maior = mais paralelismo de
    # gravação/reprocessamento; em produção dimensionar junto ao lado do banco.
    pool_min: int = 2
    pool_max: int = 10


@lru_cache
def obter_settings() -> Settings:
    """Retorna as settings em cache (uma única leitura de ambiente)."""
    return Settings()
