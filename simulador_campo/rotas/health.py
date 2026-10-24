"""Rota de saúde do simulador (sem autenticação)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from persistencia import contar_apontamentos

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    """Status do serviço, do SQLite, do gerador e do modo indisponível.

    Única rota sem exigência de X-API-Key; permanece acessível durante o
    modo indisponível, informando `modo_indisponivel_ate` (ISO-8601) — null
    quando não há indisponibilidade ativa.
    """
    ate = getattr(request.app.state, "modo_indisponivel_ate", None)
    ativo = ate if ate is not None and datetime.now(timezone.utc) < ate else None
    return {
        "status": "ok",
        "sqlite": "ok",
        "gerador": "ok",
        "total_apontamentos": contar_apontamentos(),
        "modo_indisponivel_ate": ativo.isoformat(timespec="microseconds").replace("+00:00", "Z")
        if ativo
        else None,
    }
