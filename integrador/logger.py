"""Logger estruturado em JSON com os campos lote_id e id_origem (3.4).

Eventos são emitidos pelo logger "integrador", passando contexto via
`extra` (ex.: logger.info("...", extra={"lote_id": 1, "id_origem": "..."}).
Campos de contexto ausentes ficam simplesmente fora do JSON; NUNCA logar
senha ou API key.
"""
import json
import logging
from datetime import datetime, timezone

NOME_LOGGER = "integrador"
CAMPOS_CONTEXTO = ("lote_id", "id_origem", "codigo_erro")


class FormatoJSON(logging.Formatter):
    """Serializa cada evento como um objeto JSON por linha."""

    def format(self, registro: logging.LogRecord) -> str:
        evento: dict = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "nivel": registro.levelname,
            "mensagem": registro.getMessage(),
        }
        for campo in CAMPOS_CONTEXTO:
            valor = getattr(registro, campo, None)
            if valor is not None:
                evento[campo] = valor
        if registro.exc_info:
            evento["excecao"] = self.formatException(registro.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar_logger(nivel: int = logging.INFO) -> logging.Logger:
    """Configura (de forma idempotente) o handler JSON do logger do integrador."""
    logger = logging.getLogger(NOME_LOGGER)
    if not any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(FormatoJSON())
        logger.addHandler(handler)
    logger.setLevel(nivel)
    return logger


def obter_logger() -> logging.Logger:
    """Retorna o logger do integrador (JSON após configurar_logger)."""
    return logging.getLogger(NOME_LOGGER)
