"""Configuração do painel (prefixo PAINEL_) e acesso read-only ao Oracle (4.2).

Conexão python-oracledb em modo THIN, criada uma única vez por processo via
@st.cache_resource. O painel executa SOMENTE consultas (SELECT) — as views de
db/06_views.sql primeiro; tabelas base apenas onde as views não cobrem a
necessidade por-item (fila, rejeições com payload, drill-down de lote).

Fuso: o banco grava tudo em UTC; TODA exibição é convertida para
America/Sao_Paulo nos pontos de exibição (nunca no SQL) — ver para_sao_paulo().
"""
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import oracledb
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict

FUSO_EXIBICAO = ZoneInfo("America/Sao_Paulo")


class Settings(BaseSettings):
    """Settings lidas do ambiente: PAINEL_ORACLE_DSN, PAINEL_INTEGRADOR_URL etc."""

    model_config = SettingsConfigDict(env_prefix="PAINEL_", extra="ignore")

    # Conexão Oracle (mesmo alvo do integrador: usuário INTEGRACAO, só SELECT).
    oracle_dsn: str = "localhost:1521/XEPDB1"
    oracle_usuario: str = "INTEGRACAO"
    # Senha fictícia da demo local, idêntica a db/01_schema.sql; em produção,
    # definir a env PAINEL_ORACLE_SENHA. NUNCA logar este valor.
    oracle_senha: str = "IntegracaoFicticia2026"

    # API administrativa do integrador (Módulo B) — usada apenas na ação de
    # reprocessamento manual (POST /reprocessar com header X-API-Key).
    integrador_url: str = "http://localhost:8002"
    integrador_api_key: str = "integrador-dev-key-001"

    # Serviço (a porta efetiva é definida ao subir o streamlit; o Dockerfile fixa 8501).
    porta: int = 8501

    # Auto-refresh: 0 = desligado; >0 = reroda o app a cada N segundos.
    auto_refresh_seg: int = 0

    # Timeout HTTP para a chamada de reprocessamento no integrador.
    timeout_http_seg: int = 10


@lru_cache
def obter_settings() -> Settings:
    """Retorna as settings em cache (uma única leitura de ambiente)."""
    return Settings()


@st.cache_resource
def obter_pool() -> oracledb.SessionPool:
    """Pool de conexões Oracle (modo thin), criado uma vez por processo."""
    cfg = obter_settings()
    return oracledb.create_pool(
        user=cfg.oracle_usuario,
        password=cfg.oracle_senha,
        dsn=cfg.oracle_dsn,
        min=1,
        max=5,
        increment=1,
    )


def consultar(sql: str, parametros: dict | None = None) -> list[dict]:
    """Executa um SELECT e devolve as linhas como dicionários (colunas minúsculas)."""
    with obter_pool().acquire() as conn:
        cur = conn.cursor()
        cur.execute(sql, parametros or {})
        colunas = [descricao[0].lower() for descricao in cur.description]
        return [dict(zip(colunas, linha)) for linha in cur.fetchall()]


def para_sao_paulo(valor: datetime | None) -> datetime | None:
    """Converte um timestamp do banco (UTC) para o fuso de exibição.

    Timestamps do Oracle chegam sem tzinfo; a ausência é tratada como UTC
    (convenção do banco da demo). A conversão é feita aqui, no ponto de
    exibição — nunca no SQL.
    """
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(FUSO_EXIBICAO)
