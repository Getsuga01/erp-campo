"""Validação de contrato e regras de negócio (3.9).

Ordem (decisão do controller): parse Pydantic (INT-001/011) →
versao_contrato (INT-009) → data futura com tolerância INT_TOLERANCIA_FUTURO_MIN
default 5 min (INT-007) → cadastros: talhão existe/ativo (INT-002/003),
equipamento existe/ativo quando presente (INT-004), item existe quando
presente (INT-005) → regras por tipo: PESAGEM peso (INT-006), MAQUINA
horas (INT-008), INSUMO quantidade (INT-010).

Peso acima de PESO_LIMITE_ALERTA gera log WARNING mas GRAVA. Campos
extras desconhecidos são ignorados com log de warning. A revalidação no
reprocessamento usa cadastros ATUAIS: cada validação consulta o banco de
novo (sem cache entre tentativas).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from config import obter_settings
from erros import ErroRejeicao
from logger import obter_logger
from models import (
    CAMPOS_CONHECIDOS,
    PayloadApontamento,
    TipoApontamento,
    VERSAO_CONTRATO_SUPORTADA,
)
from oracle_client import sessao

logger = obter_logger()

# Tolerância numérica (em kg) na conferência peso_liquido = bruto - tara,
# absorvendo arredondamentos de 3 casas do contrato.
TOLERANCIA_PESO = 0.001


@dataclass
class RegistroValidado:
    """Payload aprovado com as FKs já resolvidas por código."""

    modelo: PayloadApontamento
    talhao_id: int
    equipamento_id: int | None
    item_id: int | None


def validar(payload: object) -> RegistroValidado:
    """Valida o payload completo; levanta ErroRejeicao com o código INT-xxx."""
    if not isinstance(payload, dict):
        raise ErroRejeicao("INT-011", "payload não é um objeto")
    modelo = _parse(payload)
    if modelo.versao_contrato != VERSAO_CONTRATO_SUPORTADA:
        raise ErroRejeicao(
            "INT-009",
            f"recebida '{modelo.versao_contrato}', suportada '{VERSAO_CONTRATO_SUPORTADA}'",
        )
    _validar_data_futura(modelo)
    talhao_id, equipamento_id, item_id = _validar_cadastros(modelo)
    _regras_por_tipo(modelo)
    return RegistroValidado(modelo, talhao_id, equipamento_id, item_id)


def _parse(payload: dict) -> PayloadApontamento:
    desconhecidos = set(payload) - set(CAMPOS_CONHECIDOS)
    if desconhecidos:
        logger.warning(
            f"campos desconhecidos ignorados: {sorted(map(str, desconhecidos))}",
            extra={"id_origem": payload.get("id_origem")},
        )
    try:
        return PayloadApontamento.model_validate(payload)
    except ValidationError as erro:
        tipos = {item["type"] for item in erro.errors()}
        if "missing" in tipos:
            ausentes = [str(item["loc"][0]) for item in erro.errors() if item["type"] == "missing"]
            raise ErroRejeicao("INT-001", f"campo(s) ausente(s): {', '.join(ausentes)}") from erro
        raise ErroRejeicao("INT-011", str(erro.errors()[:3])) from erro


def _validar_data_futura(modelo: PayloadApontamento) -> None:
    cfg = obter_settings()
    momento = modelo.data_hora
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    limite = datetime.now(timezone.utc) + timedelta(minutes=cfg.tolerancia_futuro_min)
    if momento > limite:
        raise ErroRejeicao(
            "INT-007",
            f"data_hora {modelo.data_hora.isoformat()} está no futuro "
            f"(tolerância de {cfg.tolerancia_futuro_min} min)",
        )


def _validar_cadastros(modelo: PayloadApontamento) -> tuple[int, int | None, int | None]:
    """Confere talhão/equipamento/item e devolve os ids resolvidos."""
    with sessao() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, ativo FROM TALHAO WHERE codigo = :codigo", {"codigo": modelo.talhao_codigo})
        talhao = cur.fetchone()
        equipamento = None
        if modelo.equipamento_codigo is not None:
            cur.execute(
                "SELECT id, ativo FROM EQUIPAMENTO WHERE codigo = :codigo",
                {"codigo": modelo.equipamento_codigo},
            )
            equipamento = cur.fetchone()
        item = None
        if modelo.item_codigo is not None:
            cur.execute(
                "SELECT id FROM ERP_SUPRIMENTOS.ITEM WHERE codigo = :codigo",
                {"codigo": modelo.item_codigo},
            )
            item = cur.fetchone()
    if talhao is None:
        raise ErroRejeicao("INT-002", f"talhão {modelo.talhao_codigo} não cadastrado")
    if int(talhao[1]) != 1:
        raise ErroRejeicao("INT-003", f"talhão {modelo.talhao_codigo} inativo")
    equipamento_id = None
    if equipamento is not None:
        if int(equipamento[1]) != 1:
            raise ErroRejeicao("INT-004", f"equipamento {modelo.equipamento_codigo} inativo")
        equipamento_id = int(equipamento[0])
    elif modelo.equipamento_codigo is not None:
        raise ErroRejeicao("INT-004", f"equipamento {modelo.equipamento_codigo} não cadastrado")
    item_id = None
    if item is not None:
        item_id = int(item[0])
    elif modelo.item_codigo is not None:
        raise ErroRejeicao("INT-005", f"item {modelo.item_codigo} não cadastrado")
    return int(talhao[0]), equipamento_id, item_id


def _regras_por_tipo(modelo: PayloadApontamento) -> None:
    cfg = obter_settings()
    if modelo.tipo == TipoApontamento.PESAGEM:
        if modelo.equipamento_codigo is None:
            raise ErroRejeicao("INT-001", "PESAGEM exige equipamento_codigo")
        if modelo.peso_bruto is None or modelo.peso_tara is None or modelo.peso_liquido is None:
            raise ErroRejeicao("INT-006", "PESAGEM exige peso_bruto, peso_tara e peso_liquido")
        esperado = modelo.peso_bruto - modelo.peso_tara
        if abs(modelo.peso_liquido - esperado) > TOLERANCIA_PESO:
            raise ErroRejeicao(
                "INT-006", f"peso_liquido {modelo.peso_liquido} != bruto - tara ({esperado})"
            )
        if modelo.peso_liquido <= 0:
            raise ErroRejeicao("INT-006", f"peso_liquido {modelo.peso_liquido} <= 0")
        if modelo.peso_bruto > cfg.peso_limite_alerta:
            logger.warning(
                f"peso acima do limite de alerta ({modelo.peso_bruto} > {cfg.peso_limite_alerta}) — gravando mesmo assim",
                extra={"id_origem": modelo.id_origem},
            )
    elif modelo.tipo == TipoApontamento.MAQUINA:
        if modelo.equipamento_codigo is None:
            raise ErroRejeicao("INT-001", "MAQUINA exige equipamento_codigo")
        if modelo.horas_maquina is None or not (0 < modelo.horas_maquina <= 24):
            raise ErroRejeicao("INT-008", f"horas_maquina {modelo.horas_maquina} fora de (0, 24]")
    else:  # INSUMO
        if modelo.item_codigo is None:
            raise ErroRejeicao("INT-001", "INSUMO exige item_codigo")
        if modelo.quantidade is None or modelo.quantidade <= 0:
            raise ErroRejeicao("INT-010", f"quantidade {modelo.quantidade} <= 0 em INSUMO")
