"""Cliente Oracle (python-oracledb em modo THIN) com pool de conexões (3.3).

O pool é criado sob demanda (permitindo o boot do serviço mesmo com o
banco fora do ar; a conexão é recuperada na primeira operação útil).
`transacao()` faz commit ao sucesso e rollback em erro; `sessao()` serve
leituras (rollback implícito ao devolver a conexão ao pool).
"""
from contextlib import contextmanager
from typing import Iterator

import oracledb

from config import obter_settings
from logger import obter_logger

logger = obter_logger()

_pool: oracledb.SessionPool | None = None


def obter_pool() -> oracledb.SessionPool:
    """Retorna o pool, criando-o na primeira chamada (modo thin, sem instant client)."""
    global _pool
    if _pool is None:
        cfg = obter_settings()
        _pool = oracledb.create_pool(
            user=cfg.oracle_usuario,
            password=cfg.oracle_senha,
            dsn=cfg.oracle_dsn,
            min=cfg.pool_min,
            max=cfg.pool_max,
            increment=1,
        )
    return _pool


def iniciar_pool() -> None:
    """Aquece o pool no boot do serviço (falha fica registrada no log)."""
    obter_pool()


def valor_retornado(variavel: oracledb.Var) -> int:
    """Extrai o id de uma bind var de RETURNING INTO (uma lista com 1 elemento)."""
    valor = variavel.getvalue()
    if isinstance(valor, list):
        valor = valor[0]
    return int(valor)


def encerrar_pool() -> None:
    """Fecha o pool no shutdown do serviço."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transacao() -> Iterator[oracledb.Connection]:
    """Transação: commit ao sucesso, rollback em exceção, devolve a sessão ao pool."""
    conn = obter_pool().acquire()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def sessao() -> Iterator[oracledb.Connection]:
    """Sessão de leitura (sem commit; rollback implícito ao sair)."""
    conn = obter_pool().acquire()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
