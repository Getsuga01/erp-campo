"""Agendador APScheduler (3.1/3.16) — BackgroundScheduler.

Jobs: ciclo de integração a cada CICLO_INTERVALO_MIN (default 5) e
reprocessador a cada REPROC_INTERVALO_MIN (default 2), iniciados no
lifespan do FastAPI e encerrados no shutdown. O job do ciclo e o
POST /ciclo/executar usam a MESMA função (ciclo.executar_ciclo); como os
jobs rodam em threads próprias, cada execução cria um event loop com
asyncio.run. max_instances=1 evita sobreposição do próprio job; a
sobreposição entre job e execução manual é evitada pelo lock interno da
função do ciclo.
"""
import asyncio

from apscheduler.schedulers.background import BackgroundScheduler

from ciclo import executar_ciclo
from config import obter_settings
from logger import obter_logger
from reprocessador import executar_reprocessamento

logger = obter_logger()

_agendador: BackgroundScheduler | None = None


def _job_ciclo() -> None:
    asyncio.run(executar_ciclo())


def _job_reprocessador() -> None:
    executar_reprocessamento()


def iniciar_agendador() -> None:
    global _agendador
    cfg = obter_settings()
    _agendador = BackgroundScheduler(timezone="UTC")
    _agendador.add_job(
        _job_ciclo,
        "interval",
        minutes=cfg.ciclo_intervalo_min,
        id="ciclo-integracao",
        max_instances=1,
    )
    _agendador.add_job(
        _job_reprocessador,
        "interval",
        minutes=cfg.reproc_intervalo_min,
        id="reprocessador",
        max_instances=1,
    )
    _agendador.start()
    logger.info(
        f"agendador iniciado: ciclo a cada {cfg.ciclo_intervalo_min} min, "
        f"reprocessador a cada {cfg.reproc_intervalo_min} min"
    )


def encerrar_agendador() -> None:
    global _agendador
    if _agendador is not None:
        _agendador.shutdown(wait=False)
        _agendador = None
        logger.info("agendador encerrado")
