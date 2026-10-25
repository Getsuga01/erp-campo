"""Camada de persistência dos apontamentos (SQLite).

Ver database.py para a decisão documentada sobre a tabela de duplicatas e o
espaço único de ids entre as duas tabelas.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from database import conectar


@contextmanager
def transacao() -> Iterator[sqlite3.Connection]:
    """Transação de escrita serializada (BEGIN IMMEDIATE)."""
    conn = conectar()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def agora_utc_iso() -> str:
    """Timestamp ISO-8601 UTC com sufixo Z (ordenável lexicograficamente)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _proximo_id_global(conn: sqlite3.Connection) -> int:
    """Próximo id do contador global compartilhado pelas duas tabelas."""
    linha = conn.execute(
        """
        SELECT COALESCE(MAX(id), 0) + 1 AS proximo FROM (
            SELECT id FROM apontamentos
            UNION ALL
            SELECT id FROM apontamentos_duplicados
        )
        """
    ).fetchone()
    return int(linha["proximo"])


def inserir_varios(itens: list[tuple[dict, bool]]) -> list[int]:
    """Insere vários apontamentos numa única transação.

    Cada item é uma tupla (payload, duplicado). `duplicado=False` grava em
    `apontamentos` (UK em id_origem); `duplicado=True` grava em
    `apontamentos_duplicados`. Retorna os ids de linha na ordem de inserção.
    Levanta sqlite3.IntegrityError se um id_origem novo violar a UK.
    """
    ids: list[int] = []
    with transacao() as conn:
        for payload, duplicado in itens:
            id_linha = _proximo_id_global(conn)
            tabela = "apontamentos_duplicados" if duplicado else "apontamentos"
            conn.execute(
                f"INSERT INTO {tabela} (id, id_origem, tipo, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    id_linha,
                    payload["id_origem"],
                    payload["tipo"],
                    json.dumps(payload, ensure_ascii=False),
                    agora_utc_iso(),
                ),
            )
            ids.append(id_linha)
    return ids


def listar_paginado(
    cursor: tuple[str, int] | None, limite: int
) -> tuple[list[dict], tuple[str, int] | None]:
    """Lista apontamentos em ordem estável (created_at, id) ascendente.

    O cursor é a tupla (created_at, id) da última linha servida. Retorna os
    payloads e o próximo cursor — SEMPRE a posição da última linha servida
    quando ao menos 1 item foi servido (inclusive na última página parcial);
    None SOMENTE quando a página veio vazia (emenda R9: o consumidor para
    quando recebe menos itens que o limite pedido).
    """
    conn = conectar()
    try:
        sql = (
            "SELECT id, created_at, payload FROM ("
            " SELECT id, created_at, payload FROM apontamentos"
            " UNION ALL"
            " SELECT id, created_at, payload FROM apontamentos_duplicados"
            ") "
        )
        parametros: list = []
        if cursor is not None:
            sql += "WHERE created_at > ? OR (created_at = ? AND id > ?) "
            parametros += [cursor[0], cursor[0], cursor[1]]
        sql += "ORDER BY created_at ASC, id ASC LIMIT ?"
        parametros.append(limite + 1)
        linhas = conn.execute(sql, parametros).fetchall()
    finally:
        conn.close()
    # Busca limite+1 apenas para fatiar em "limite" linhas servidas (o excesso
    # é descartado); a sinalização de "tem mais" deixou de ser necessária — o
    # consumidor para quando recebe menos itens que o limite (emenda R9).
    linhas = linhas[:limite]
    itens = [json.loads(linha["payload"]) for linha in linhas]
    # Emenda R9: o cursor retornado é a posição da ÚLTIMA LINHA SERVIDA,
    # sem condicionar a "existe próxima página" — assim o consumidor pode
    # avançar seu cursor para uma posição exata mesmo quando os dados
    # acabam no meio de uma página. None apenas quando nada foi servido.
    proximo_cursor = (
        (linhas[-1]["created_at"], int(linhas[-1]["id"])) if linhas else None
    )
    return itens, proximo_cursor


def buscar_por_id_origem(id_origem: str) -> dict | None:
    """Busca um apontamento pelo id_origem (prefere a linha original)."""
    conn = conectar()
    try:
        linha = conn.execute(
            "SELECT payload FROM apontamentos WHERE id_origem = ? "
            "UNION ALL "
            "SELECT payload FROM apontamentos_duplicados WHERE id_origem = ? "
            "LIMIT 1",
            (id_origem, id_origem),
        ).fetchone()
    finally:
        conn.close()
    return json.loads(linha["payload"]) if linha else None


def contar_apontamentos() -> int:
    """Total de linhas nas duas tabelas (originais + duplicatas)."""
    conn = conectar()
    try:
        linha = conn.execute(
            "SELECT (SELECT COUNT(*) FROM apontamentos) "
            " + (SELECT COUNT(*) FROM apontamentos_duplicados) AS total"
        ).fetchone()
    finally:
        conn.close()
    return int(linha["total"])


def sortear_registro_existente() -> dict | None:
    """Retorna o payload de um registro existente qualquer (para DUPLICATA)."""
    conn = conectar()
    try:
        linha = conn.execute(
            "SELECT payload FROM ("
            " SELECT id_origem, payload FROM apontamentos"
            " UNION ALL"
            " SELECT id_origem, payload FROM apontamentos_duplicados"
            ") ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return json.loads(linha["payload"]) if linha else None
