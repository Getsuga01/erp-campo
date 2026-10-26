"""Rotas administrativas de lotes (3.19/3.20)."""
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from oracle_client import sessao
from rotas import linha_para_dict

router = APIRouter()

_SQL_LISTAR = (
    "SELECT id, status, iniciado_em, fechado_em, total_recebidos, total_gravados, "
    "       total_rejeitados, total_duplicados, cursor_inicio, cursor_fim, observacao "
    "  FROM INT_LOTE "
    " WHERE (:status IS NULL OR status = :status) "
    "   AND (:de IS NULL OR iniciado_em >= :de) "
    "   AND (:ate IS NULL OR iniciado_em < :ate) "
    " ORDER BY id DESC "
    " OFFSET :offset ROWS FETCH NEXT :limite ROWS ONLY"
)
_SQL_TOTAL = (
    "SELECT COUNT(*) FROM INT_LOTE "
    " WHERE (:status IS NULL OR status = :status) "
    "   AND (:de IS NULL OR iniciado_em >= :de) "
    "   AND (:ate IS NULL OR iniciado_em < :ate)"
)


def _para_data(valor: str | None, campo: str) -> datetime | None:
    if valor is None:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"parametro {campo} deve ser AAAA-MM-DD") from None


@router.get("/lotes")
def listar_lotes(
    status: str | None = Query(default=None, description="EM_ANDAMENTO/CONCLUIDO/FALHOU"),
    de: str | None = Query(default=None, description="AAAA-MM-DD (iniciado_em a partir de)"),
    ate: str | None = Query(default=None, description="AAAA-MM-DD (iniciado_em até, exclusivo)"),
    limite: int = Query(default=50, ge=1, le=200),
    pagina: int = Query(default=1, ge=1),
) -> dict:
    """Lista lotes com filtros e paginação; retorna o total de linhas."""
    filtros = {
        "status": status,
        "de": _para_data(de, "de"),
        "ate": _para_data(ate, "ate") + timedelta(days=1) if ate else None,
    }
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute(_SQL_TOTAL, filtros)
        total = int(cur.fetchone()[0])
        cur.execute(_SQL_LISTAR, {**filtros, "offset": (pagina - 1) * limite, "limite": limite})
        descricao = cur.description
        itens = [linha_para_dict(linha, descricao) for linha in cur.fetchall()]
    return {"itens": itens, "total": total}


@router.get("/lotes/{lote_id}")
def obter_lote(lote_id: int) -> dict:
    """Detalhe do lote + lista dos registros vinculados."""
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, status, iniciado_em, fechado_em, total_recebidos, total_gravados, "
            "       total_rejeitados, total_duplicados, cursor_inicio, cursor_fim, observacao "
            "  FROM INT_LOTE WHERE id = :lote",
            {"lote": lote_id},
        )
        lote = cur.fetchone()
        if lote is None:
            raise HTTPException(status_code=404, detail="lote nao encontrado")
        lote_dict = linha_para_dict(lote, cur.description)
        cur.execute(
            "SELECT id, lote_id, id_origem, tipo, status, codigo_erro, mensagem_erro, "
            "       recebido_em, processado_em, origem "
            "  FROM INT_REGISTRO WHERE lote_id = :lote ORDER BY id",
            {"lote": lote_id},
        )
        descricao = cur.description
        registros = [linha_para_dict(linha, descricao) for linha in cur.fetchall()]
    return {"lote": lote_dict, "registros": registros}
