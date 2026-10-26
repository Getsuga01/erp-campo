"""Rota de reprocessamento manual (3.24)."""
from fastapi import APIRouter

from models import ReprocessarRequest
from reprocessador import reprocessar_manual

router = APIRouter()


@router.post("/reprocessar")
def reprocessar(corpo: ReprocessarRequest) -> dict:
    """Reprocessa registros específicos com motivo obrigatório.

    Valida existência e estado (fila em PENDENTE/DEAD_LETTER ou registro
    REJEITADO), reseta tentativas se DEAD_LETTER, agenda tentativa
    imediata e registra a tentativa em INT_TENTATIVA com acionado_por
    MANUAL e o motivo na observacao.
    """
    resultados = reprocessar_manual(corpo.registro_ids, corpo.motivo, corpo.acionado_por)
    reprocessados = sum(1 for item in resultados if item["resultado"] in ("SUCESSO", "FALHA"))
    return {"reprocessados": reprocessados, "resultados": resultados}
