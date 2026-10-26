"""Rota de saúde do integrador (3.18) — sem autenticação."""
import httpx
import oracledb
from fastapi import APIRouter

from config import obter_settings
from oracle_client import sessao

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Status do serviço, do Oracle e da origem (API do sistema de campo)."""
    oracle = "ok"
    try:
        with sessao() as conn:
            conn.cursor().execute("SELECT 1 FROM DUAL").fetchone()
    except oracledb.Error:
        oracle = "erro"
    origem = "ok"
    try:
        httpx.get(f"{obter_settings().campo_url}/health", timeout=3)
    except httpx.HTTPError:
        origem = "erro"
    status = "ok" if oracle == "ok" and origem == "ok" else "degradado"
    return {"status": status, "oracle": oracle, "origem": origem}
