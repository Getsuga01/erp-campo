"""Rotas de controle do simulador: gerar, injetar falhas e indisponibilidade."""
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from falhas import injetar
from gerador import gerar_lote
from models import GerarRequest, InjetarFalhaRequest, ModoIndisponivelRequest
from persistencia import inserir_varios

router = APIRouter()


@router.post("/simulador/gerar")
def gerar(corpo: GerarRequest) -> dict:
    """Gera N apontamentos VÁLIDOS e os persiste no SQLite.

    Exemplo:
        {"quantidade": 100, "semente": 42}
        {"quantidade": 50, "tipos": ["PESAGEM", "MAQUINA"]}
    Mesma semente + mesma quantidade → mesmos id_origem e valores.
    """
    registros = gerar_lote(corpo.quantidade, corpo.semente, corpo.tipos)
    try:
        inserir_varios([(registro, False) for registro in registros])
    except sqlite3.IntegrityError as erro:
        # Gerar a mesma semente sem limpar a base choca na UK de id_origem.
        raise HTTPException(
            status_code=409,
            detail="id_origem duplicado ao gerar (semente repetida sem limpar a base); "
            "use outra semente ou reinicie a base",
        ) from erro
    return {
        "gerados": len(registros),
        "ids_origem": [registro["id_origem"] for registro in registros],
    }


@router.post("/simulador/injetar-falha")
def injetar_falha(corpo: InjetarFalhaRequest) -> dict:
    """Gera registros que VIOLAM uma regra específica e os persiste.

    Tipos: TALHAO_INEXISTENTE, PESO_NEGATIVO, DUPLICATA, DATA_FUTURA,
    CAMPO_AUSENTE, ITEM_INEXISTENTE, HORAS_INVALIDAS.

    Exemplo:
        {"tipo_falha": "PESO_NEGATIVO", "quantidade": 3}
    """
    ids = injetar(corpo.tipo_falha, corpo.quantidade)
    return {
        "tipo_falha": corpo.tipo_falha.value,
        "injetados": len(ids),
        "ids_origem": ids,
    }


@router.post("/simulador/modo-indisponivel")
def modo_indisponivel(corpo: ModoIndisponivelRequest, request: Request) -> dict:
    """Coloca o simulador em modo indisponível por N segundos (503 geral).

    Estado em memória: reiniciar o serviço limpa o modo. `/health` continua
    respondendo e expõe `modo_indisponivel_ate`.

    Exemplo:
        {"duracao_segundos": 60}
    """
    ate = datetime.now(timezone.utc) + timedelta(seconds=corpo.duracao_segundos)
    request.app.state.modo_indisponivel_ate = ate
    request.app.state.duracao_modo_indisponivel = corpo.duracao_segundos
    return {
        "modo_indisponivel_ate": ate.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "duracao_segundos": corpo.duracao_segundos,
    }
