"""Modelos Pydantic do contrato de dados do apontamento.

O contrato é FIXO e compartilhado com o integrador (Módulo B). Regras de
negócio (códigos existentes, ativos etc.) NÃO são validadas aqui — são papel
do integrador. Os validadores abaixo servem apenas para garantir que o
GERADOR NORMAL produza registros que passariam na validação do integrador.
O injetor de falhas trabalha sobre dicionários (pós-modelo), então os
registros inválidos circulam sem ser bloqueados pelo simulador.
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

VERSAO_CONTRATO = "1.0"


class TipoApontamento(str, Enum):
    """Tipos de apontamento suportados pelo contrato."""

    PESAGEM = "PESAGEM"
    MAQUINA = "MAQUINA"
    INSUMO = "INSUMO"


class TipoFalha(str, Enum):
    """Falhas que o injetor sabe produzir (cada uma viola uma regra)."""

    TALHAO_INEXISTENTE = "TALHAO_INEXISTENTE"
    PESO_NEGATIVO = "PESO_NEGATIVO"
    DUPLICATA = "DUPLICATA"
    DATA_FUTURA = "DATA_FUTURA"
    CAMPO_AUSENTE = "CAMPO_AUSENTE"
    ITEM_INEXISTENTE = "ITEM_INEXISTENTE"
    HORAS_INVALIDAS = "HORAS_INVALIDAS"


class Apontamento(BaseModel):
    """Payload de um apontamento (contrato v1.0).

    Campos irrelevantes ao tipo seguem como null (nunca omitidos).
    """

    id_origem: str = Field(description="UUID4 gerado pelo sistema de campo")
    tipo: TipoApontamento
    data_hora: str = Field(description="ISO-8601 UTC, ex.: 2026-10-24T14:30:00Z")
    talhao_codigo: str = Field(description="TAL-001..TAL-020 (ver db/07_carga_mestres.sql)")
    equipamento_codigo: str | None = Field(
        default=None, description="EQP-001..EQP-015; obrigatório em PESAGEM/MAQUINA, null em INSUMO"
    )
    item_codigo: str | None = Field(
        default=None, description="ITEM-001..ITEM-010; obrigatório em INSUMO, null nos demais"
    )
    peso_bruto: float | None = Field(default=None, description="number(12,3) — apenas PESAGEM")
    peso_tara: float | None = Field(default=None, description="number(12,3) — apenas PESAGEM")
    peso_liquido: float | None = Field(default=None, description="number(12,3) — apenas PESAGEM (bruto - tara > 0)")
    horas_maquina: float | None = Field(default=None, description="number(6,2), 0 < h <= 24 — apenas MAQUINA")
    quantidade: float | None = Field(default=None, description="number(12,3) > 0 — apenas INSUMO")
    operador: str = Field(description="Nome fictício do operador")
    observacao: str | None = None
    versao_contrato: Literal["1.0"] = VERSAO_CONTRATO

    @model_validator(mode="after")
    def _validar_estrutura_por_tipo(self) -> "Apontamento":
        """Garante que um registro NORMAL é estruturalmente válido.

        Valida apenas o que o gerador promete produzir; códigos de mestre
        (existência/ativo) e datas ficam fora — responsabilidade do integrador.
        """
        if self.tipo == TipoApontamento.PESAGEM:
            if not self.equipamento_codigo:
                raise ValueError("PESAGEM exige equipamento_codigo")
            if None in (self.peso_bruto, self.peso_tara, self.peso_liquido):
                raise ValueError("PESAGEM exige peso_bruto, peso_tara e peso_liquido")
            if any(
                getattr(self, campo) is not None
                for campo in ("item_codigo", "horas_maquina", "quantidade")
            ):
                raise ValueError("PESAGEM não usa item_codigo, horas_maquina nem quantidade")
            liquido = round(self.peso_bruto - self.peso_tara, 3)
            if self.peso_liquido <= 0 or abs(self.peso_liquido - liquido) > 1e-6:
                raise ValueError("peso_liquido deve ser igual a bruto - tara e ser > 0")
        elif self.tipo == TipoApontamento.MAQUINA:
            if not self.equipamento_codigo:
                raise ValueError("MAQUINA exige equipamento_codigo")
            if self.horas_maquina is None or not (0 < self.horas_maquina <= 24):
                raise ValueError("horas_maquina deve estar em (0, 24]")
            if any(
                getattr(self, campo) is not None
                for campo in ("item_codigo", "peso_bruto", "peso_tara", "peso_liquido", "quantidade")
            ):
                raise ValueError("MAQUINA não usa item_codigo, pesos nem quantidade")
        else:  # INSUMO
            if not self.item_codigo:
                raise ValueError("INSUMO exige item_codigo")
            if self.quantidade is None or self.quantidade <= 0:
                raise ValueError("quantidade deve ser > 0")
            if any(
                getattr(self, campo) is not None
                for campo in ("equipamento_codigo", "peso_bruto", "peso_tara", "peso_liquido", "horas_maquina")
            ):
                raise ValueError("INSUMO não usa equipamento_codigo, pesos nem horas_maquina")
        return self


class GerarRequest(BaseModel):
    """Corpo de POST /simulador/gerar."""

    quantidade: int = Field(default=100, ge=1, le=1000)
    semente: int = 42
    tipos: list[TipoApontamento] | None = Field(
        default=None, description="Default: todos (distribuição ~40/30/30)"
    )


class InjetarFalhaRequest(BaseModel):
    """Corpo de POST /simulador/injetar-falha."""

    tipo_falha: TipoFalha
    quantidade: int = Field(default=1, ge=1, le=100)


class ModoIndisponivelRequest(BaseModel):
    """Corpo de POST /simulador/modo-indisponivel."""

    duracao_segundos: int = Field(default=60, ge=1, le=3600)
