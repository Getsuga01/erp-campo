"""Serviço de Integração (Módulo B) — API administrativa na porta 8002.

Demo fictícia: consome a API do simulador do sistema de campo (Módulo A),
valida, grava no Oracle, gerencia rejeições/fila/dead-letter e expõe a
API administrativa (lotes, registros, fila, ciclo, reprocessamento,
conciliação e métricas).

Como rodar (imports top-level absolutos — igual ao simulador):
    uvicorn --app-dir integrador main:app --port 8002

Autenticação: header X-API-Key igual à env INT_API_KEY (demo:
"integrador-dev-key-001"). Exceção: GET /health.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

import oracle_client
from agendador import encerrar_agendador, iniciar_agendador
from config import obter_settings
from logger import configurar_logger, obter_logger
from rotas.ciclo import router as router_ciclo
from rotas.conciliacao import router as router_conciliacao
from rotas.fila import router as router_fila
from rotas.health import router as router_health
from rotas.lotes import router as router_lotes
from rotas.metricas import router as router_metricas
from rotas.registros import router as router_registros
from rotas.reprocessar import router as router_reprocessar

configurar_logger()
logger = obter_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: pool Oracle e agendador; shutdown: o inverso."""
    try:
        oracle_client.iniciar_pool()
        logger.info("pool Oracle iniciado")
    except Exception as erro:
        logger.critical(f"pool Oracle nao pôde ser criado no boot ({type(erro).__name__}); tentará sob demanda")
    iniciar_agendador()
    yield
    encerrar_agendador()
    oracle_client.encerrar_pool()
    logger.info("integrador encerrado")


app = FastAPI(
    title="Serviço de Integração Campo → ERP",
    version="1.0.0",
    description="Módulo B: consome a API do sistema de campo, valida, grava no Oracle e expõe API administrativa.",
    lifespan=lifespan,
)


def verificar_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Exige header X-API-Key válido em todas as rotas, exceto /health."""
    if not x_api_key or x_api_key != obter_settings().api_key:
        raise HTTPException(status_code=401, detail="X-API-Key ausente ou invalida")


@app.exception_handler(HTTPException)
async def handler_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """Serializa erros com a chave "detalhe" (padrão do contrato da demo)."""
    return JSONResponse(status_code=exc.status_code, content={"detalhe": exc.detail})


app.include_router(router_health)
app.include_router(router_lotes, dependencies=[Depends(verificar_api_key)])
app.include_router(router_registros, dependencies=[Depends(verificar_api_key)])
app.include_router(router_fila, dependencies=[Depends(verificar_api_key)])
app.include_router(router_ciclo, dependencies=[Depends(verificar_api_key)])
app.include_router(router_reprocessar, dependencies=[Depends(verificar_api_key)])
app.include_router(router_conciliacao, dependencies=[Depends(verificar_api_key)])
app.include_router(router_metricas, dependencies=[Depends(verificar_api_key)])
