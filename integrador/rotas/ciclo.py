"""Rota de disparo manual do ciclo (3.23)."""
from fastapi import APIRouter, HTTPException

from ciclo import executar_ciclo

router = APIRouter()


@router.post("/ciclo/executar")
async def executar() -> dict:
    """Dispara um ciclo imediato — a MESMA função executada pelo job agendado."""
    resultado = await executar_ciclo()
    if resultado.get("status") == "JA_EM_ANDAMENTO":
        raise HTTPException(status_code=409, detail="ciclo ja em andamento")
    return resultado
