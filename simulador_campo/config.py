"""Configuração do simulador via variáveis de ambiente (prefixo CAMPO_)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings lidas do ambiente: CAMPO_API_KEY, CAMPO_PORTA e CAMPO_DB_PATH."""

    model_config = SettingsConfigDict(env_prefix="CAMPO_", extra="ignore")

    # Chave exigida no header X-API-Key. O valor abaixo é o padrão de demo,
    # documentado para facilitar o desenvolvimento local; em produção real,
    # definir a env CAMPO_API_KEY.
    api_key: str = "campo-dev-key-001"

    # Porta informativa do serviço; a porta efetiva é definida ao subir o
    # uvicorn (Dockerfile fixa 8001).
    porta: int = 8001

    # Caminho do SQLite (relativo à pasta do módulo quando não absoluto).
    db_path: str = "data/simulador.db"


@lru_cache
def obter_settings() -> Settings:
    """Retorna as settings em cache (uma única leitura de ambiente)."""
    return Settings()
