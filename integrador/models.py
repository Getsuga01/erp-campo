"""Modelos Pydantic do payload recebido da origem (contrato v1.0).

Diferente do simulador (Módulo A), aqui NÃO há validador estrutural por
tipo na leitura do payload: peso/horas/quantidade inválidos produzem os
códigos de negócio INT-006/008/010 no validador (com mensagens próprias),
e campos desconhecidos são apenas ignorados com log de warning (regra do
plano). `versao_contrato` é lido como string livre para permitir a
detecção do INT-009.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

VERSAO_CONTRATO_SUPORTADA = "1.0"


class TipoApontamento(str, Enum):
    """Tipos de apontamento suportados pelo contrato."""

    PESAGEM = "PESAGEM"
    MAQUINA = "MAQUINA"
    INSUMO = "INSUMO"


CAMPOS_CONHECIDOS = frozenset(
    {
        "id_origem",
        "tipo",
        "data_hora",
        "talhao_codigo",
        "equipamento_codigo",
        "item_codigo",
        "peso_bruto",
        "peso_tara",
        "peso_liquido",
        "horas_maquina",
        "quantidade",
        "operador",
        "observacao",
        "versao_contrato",
    }
)


class PayloadApontamento(BaseModel):
    """Payload bruto do apontamento — a validação de negócio fica no validador."""

    model_config = ConfigDict(extra="ignore")

    id_origem: str
    tipo: TipoApontamento
    data_hora: datetime
    talhao_codigo: str
    equipamento_codigo: str | None = None
    item_codigo: str | None = None
    peso_bruto: float | None = None
    peso_tara: float | None = None
    peso_liquido: float | None = None
    horas_maquina: float | None = None
    quantidade: float | None = None
    operador: str
    observacao: str | None = None
    versao_contrato: str


class ReprocessarRequest(BaseModel):
    """Corpo de POST /reprocessar (3.24)."""

    registro_ids: list[int] = Field(min_length=1)
    motivo: str = Field(min_length=1, max_length=500)
    acionado_por: str = Field(default="manual", max_length=100)
