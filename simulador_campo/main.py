"""Simulador do Sistema de Campo (Módulo A) — API FastAPI na porta 8001.

Demo fictícia: origem do pipeline Sistema de Campo → ERP. Gera e serve
apontamentos (PESAGEM/MAQUINA/INSUMO) com injeção controlada de falhas.

Como rodar (imports top-level absolutos — executar a partir da pasta do
módulo, ou apontar --app-dir para ela):
    cd simulador_campo && uvicorn main:app --port 8001
    uvicorn --app-dir simulador_campo main:app --port 8001

Autenticação: header X-API-Key igual à env CAMPO_API_KEY (demo:
"campo-dev-key-001"). Exceção: GET /health.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from config import obter_settings
from database import iniciar_banco
from rotas.apontamentos import router as router_apontamentos
from rotas.health import router as router_health
from rotas.simulador import router as router_simulador


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: garante a pasta data/ e as tabelas do SQLite."""
    iniciar_banco()
    app.state.modo_indisponivel_ate = None
    app.state.duracao_modo_indisponivel = None
    yield


app = FastAPI(
    title="Simulador do Sistema de Campo",
    version="1.0.0",
    description="API fictícia de origem para a integração Sistema de Campo → ERP.",
    lifespan=lifespan,
)


def verificar_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Exige header X-API-Key válido em todas as rotas, exceto /health."""
    if not x_api_key or x_api_key != obter_settings().api_key:
        raise HTTPException(status_code=401, detail="X-API-Key ausente ou invalida")


@app.middleware("http")
async def middleware_modo_indisponivel(request: Request, call_next: Callable) -> Response:
    """Durante o modo indisponível, responde 503 em tudo, exceto /health."""
    ate = getattr(request.app.state, "modo_indisponivel_ate", None)
    if ate is not None and datetime.now(timezone.utc) < ate and request.url.path != "/health":
        duracao = getattr(request.app.state, "duracao_modo_indisponivel", 0)
        return JSONResponse(
            status_code=503,
            content={"detalhe": f"simulador em modo indisponivel por {duracao} segundos"},
        )
    return await call_next(request)


@app.exception_handler(HTTPException)
async def handler_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """Serializa erros com a chave "detalhe" (padrão do contrato da demo)."""
    return JSONResponse(status_code=exc.status_code, content={"detalhe": exc.detail})


app.include_router(router_apontamentos, dependencies=[Depends(verificar_api_key)])
app.include_router(router_simulador, dependencies=[Depends(verificar_api_key)])
app.include_router(router_health)
