"""Rotas de leitura dos apontamentos (consumidas pelo integrador)."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from persistencia import buscar_por_id_origem, listar_paginado

router = APIRouter()


@router.get("/apontamentos")
def listar_apontamentos(
    cursor: str | None = Query(default=None, description="created_at|id da página anterior"),
    limite: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Lista apontamentos em ordem de ingestão com paginação por cursor.

    Contrato fixo: resposta `{"itens": [<apontamento>...], "proximo_cursor": "<CURSOR>|null"}`.
    O cursor é `created_at|id` da última linha servida; `proximo_cursor` é
    null quando não há mais registros.

    Exemplo:
        GET /apontamentos?limite=100
        GET /apontamentos?cursor=2026-10-24T14:30:00.000001Z|42&limite=100
    """
    cursor_tupla: tuple[str, int] | None = None
    if cursor is not None:
        partes = cursor.split("|", 1)
        if len(partes) != 2 or not partes[1].isdigit():
            raise HTTPException(status_code=400, detail="cursor invalido")
        try:
            datetime.fromisoformat(partes[0].replace("Z", "+00:00"))
        except ValueError as erro:
            raise HTTPException(status_code=400, detail="cursor invalido") from erro
        cursor_tupla = (partes[0], int(partes[1]))
    itens, proximo = listar_paginado(cursor_tupla, limite)
    return {
        "itens": itens,
        "proximo_cursor": f"{proximo[0]}|{proximo[1]}" if proximo else None,
    }


@router.get("/apontamentos/{id_origem}")
def obter_apontamento(id_origem: str) -> dict:
    """Retorna o payload de um apontamento pelo id_origem (UUID).

    Respostas: 200 com o payload; 404 com `{"detalhe": "apontamento nao encontrado"}`.

    Exemplo:
        GET /apontamentos/3f2a...-...-...
    """
    payload = buscar_por_id_origem(id_origem)
    if payload is None:
        raise HTTPException(status_code=404, detail="apontamento nao encontrado")
    return payload
