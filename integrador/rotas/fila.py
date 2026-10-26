"""Rota administrativa da fila de reprocessamento (3.22)."""
from fastapi import APIRouter, Query

from oracle_client import sessao
from rotas import linha_para_dict

router = APIRouter()

_SQL = (
    "SELECT f.id, f.registro_id, r.id_origem, r.tipo, f.situacao, f.tentativas, "
    "       f.max_tentativas, f.proxima_tentativa, f.motivo, f.criado_em, f.atualizado_em "
    "  FROM FILA_REPROCESSAMENTO f JOIN INT_REGISTRO r ON r.id = f.registro_id "
    " WHERE (:situacao IS NULL OR f.situacao = :situacao) "
    " ORDER BY f.id "
    " OFFSET :offset ROWS FETCH NEXT :limite ROWS ONLY"
)
_SQL_TOTAL = (
    "SELECT COUNT(*) FROM FILA_REPROCESSAMENTO f "
    " WHERE (:situacao IS NULL OR f.situacao = :situacao)"
)


@router.get("/fila")
def listar_fila(
    situacao: str | None = Query(default=None, description="PENDENTE/PROCESSANDO/CONCLUIDA/DEAD_LETTER"),
    limite: int = Query(default=50, ge=1, le=200),
    pagina: int = Query(default=1, ge=1),
) -> dict:
    """Lista itens da fila com filtro por situação."""
    filtros = {"situacao": situacao}
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute(_SQL_TOTAL, filtros)
        total = int(cur.fetchone()[0])
        cur.execute(_SQL, {**filtros, "offset": (pagina - 1) * limite, "limite": limite})
        descricao = cur.description
        itens = [linha_para_dict(linha, descricao) for linha in cur.fetchall()]
    return {"itens": itens, "total": total}
