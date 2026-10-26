"""Rota administrativa de registros (3.21)."""
from fastapi import APIRouter, Query

from oracle_client import sessao
from rotas import linha_para_dict

router = APIRouter()

_SQL = (
    "SELECT id, lote_id, id_origem, tipo, status, codigo_erro, mensagem_erro, "
    "       recebido_em, processado_em, origem "
    "  FROM INT_REGISTRO "
    " WHERE (:status IS NULL OR status = :status) "
    "   AND (:tipo IS NULL OR tipo = :tipo) "
    "   AND (:codigo_erro IS NULL OR codigo_erro = :codigo_erro) "
    " ORDER BY id DESC "
    " OFFSET :offset ROWS FETCH NEXT :limite ROWS ONLY"
)
_SQL_TOTAL = (
    "SELECT COUNT(*) FROM INT_REGISTRO "
    " WHERE (:status IS NULL OR status = :status) "
    "   AND (:tipo IS NULL OR tipo = :tipo) "
    "   AND (:codigo_erro IS NULL OR codigo_erro = :codigo_erro)"
)


@router.get("/registros")
def listar_registros(
    status: str | None = Query(default=None, description="RECEBIDO/GRAVADO/REJEITADO/DUPLICADO/PENDENTE_FILA"),
    tipo: str | None = Query(default=None, description="PESAGEM/MAQUINA/INSUMO"),
    codigo_erro: str | None = Query(default=None, description="ex.: INT-002"),
    limite: int = Query(default=50, ge=1, le=200),
    pagina: int = Query(default=1, ge=1),
) -> dict:
    """Lista registros de integração com filtros e paginação."""
    filtros = {"status": status, "tipo": tipo, "codigo_erro": codigo_erro}
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute(_SQL_TOTAL, filtros)
        total = int(cur.fetchone()[0])
        cur.execute(_SQL, {**filtros, "offset": (pagina - 1) * limite, "limite": limite})
        descricao = cur.description
        itens = [linha_para_dict(linha, descricao) for linha in cur.fetchall()]
    return {"itens": itens, "total": total}
