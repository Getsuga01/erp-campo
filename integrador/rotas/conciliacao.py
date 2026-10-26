"""Rota de conciliação origem × destino (3.25)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from oracle_client import sessao
from rotas import linha_para_dict

router = APIRouter()

_SQL = (
    "SELECT dia, tipo, recebidos, gravados, duplicados, rejeitados, pendentes_fila, divergencia "
    "  FROM V_CONCILIACAO_DIA_TIPO "
    " WHERE (:de IS NULL OR dia >= :de) "
    "   AND (:ate IS NULL OR dia < :ate) "
    " ORDER BY dia, tipo"
)


def _para_data(valor: str | None, campo: str) -> datetime | None:
    if valor is None:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"parametro {campo} deve ser AAAA-MM-DD") from None


@router.get("/conciliacao")
def conciliacao(
    de: str | None = Query(default=None, description="AAAA-MM-DD"),
    ate: str | None = Query(default=None, description="AAAA-MM-DD (exclusivo)"),
) -> dict:
    """Retorna a conciliação por dia (UTC) × tipo a partir da view.

    A equação recebidos = gravados + duplicados + rejeitados +
    pendentes_fila é garantida pela própria view (divergencia sempre 0).
    """
    filtros = {
        "de": _para_data(de, "de"),
        "ate": _para_data(ate, "ate") + timedelta(days=1) if ate else None,
    }
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute(_SQL, filtros)
        descricao = cur.description
        itens = [linha_para_dict(linha, descricao) for linha in cur.fetchall()]
    total_divergencias = sum(int(item["divergencia"]) for item in itens)
    return {"itens": itens, "total_divergencias": total_divergencias}
