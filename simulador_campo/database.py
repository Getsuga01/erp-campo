"""Setup do SQLite — conexões e criação de schema.

Persistência local do simulador; sobrevive a reinícios (arquivo em disco).

DECISÃO DOCUMENTADA (falha DUPLICATA): a tabela `apontamentos` mantém a UK em
`id_origem` conforme o schema do plano. Duplicatas são gravadas na tabela
auxiliar `apontamentos_duplicados` (mesma estrutura, sem UK), preservando a
linha original e expondo a duplicidade na listagem — quem detecta é o
integrador. Para o cursor de paginação `(created_at, id)` continuar único e
estável no UNION das duas tabelas, TODO id de linha é alocado a partir de um
único contador global (máximo das duas tabelas + 1), inclusive os inseridos
na tabela principal (o AUTOINCREMENT fica apenas como salvaguarda).
"""
import sqlite3
from pathlib import Path

from config import obter_settings

DDL_APONTAMENTOS = """
CREATE TABLE IF NOT EXISTS apontamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_origem TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

DDL_APONTAMENTOS_DUPLICADOS = """
CREATE TABLE IF NOT EXISTS apontamentos_duplicados (
    id INTEGER PRIMARY KEY,
    id_origem TEXT NOT NULL,
    tipo TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def caminho_banco() -> Path:
    """Caminho absoluto do SQLite (relativo à pasta do módulo por padrão)."""
    caminho = Path(obter_settings().db_path)
    if not caminho.is_absolute():
        caminho = Path(__file__).resolve().parent / caminho
    return caminho


def conectar() -> sqlite3.Connection:
    """Abre uma conexão nova (uma por operação) em modo autocommit.

    Transações de escrita usam BEGIN IMMEDIATE explícito (ver persistencia.py)
    para serializar a alocação de ids entre threads do FastAPI.
    """
    caminho = caminho_banco()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(caminho, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def iniciar_banco() -> None:
    """Cria as tabelas (idempotente) — chamado no startup e em testes."""
    conn = conectar()
    try:
        conn.execute(DDL_APONTAMENTOS)
        conn.execute(DDL_APONTAMENTOS_DUPLICADOS)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_apontamentos_ordem ON apontamentos (created_at, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_apontamentos_duplicados_ordem "
            "ON apontamentos_duplicados (created_at, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_apontamentos_duplicados_id_origem "
            "ON apontamentos_duplicados (id_origem)"
        )
    finally:
        conn.close()
