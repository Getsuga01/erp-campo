"""Gerador de apontamentos fictícios com semente fixa (reprodutível).

Reprodutibilidade: com a mesma semente e a mesma quantidade, os MESMOS
registros (id_origem/UUIDs e valores incluídos) são gerados em qualquer
execução. EXCEÇÃO DOCUMENTADA: `data_hora` é derivada de um offset aleatório
(sempre o mesmo offset, da semente) aplicado a um "agora" congelado no início
da geração — logo, entre execuções em instantes diferentes, o que se repete é
o offset e os demais valores, não o instante absoluto. O `created_at` de
linha segue o mesmo raciocínio (instante real da ingestão).

Códigos de mestre: o gerador normal usa APENAS códigos ATIVOS dos cadastros
fictícios de db/07_carga_mestres.sql (TAL-001..TAL-018, EQP-001..EQP-014,
ITEM-001..ITEM-010), garantindo que registros normais passariam na validação
do integrador. Códigos inativos (TAL-019/TAL-020/EQP-015) pertencem ao
domínio do contrato, mas não são emitidos aqui.
"""
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from faker import Faker

from models import Apontamento, TipoApontamento, VERSAO_CONTRATO

# Códigos ATIVOS conforme db/07_carga_mestres.sql.
TALHOES_ATIVOS = [f"TAL-{indice:03d}" for indice in range(1, 19)]  # TAL-001..TAL-018
EQUIPAMENTOS_ATIVOS = [f"EQP-{indice:03d}" for indice in range(1, 15)]  # EQP-001..EQP-014
ITENS_ATIVOS = [f"ITEM-{indice:03d}" for indice in range(1, 11)]  # ITEM-001..ITEM-010 (todos ativos)

# Distribuição alvo ~40/30/30 entre PESAGEM/MAQUINA/INSUMO.
PESOS_TIPO: dict[TipoApontamento, int] = {
    TipoApontamento.PESAGEM: 40,
    TipoApontamento.MAQUINA: 30,
    TipoApontamento.INSUMO: 30,
}


def formatar_data_hora(momento: datetime) -> str:
    """Formata um datetime UTC como ISO-8601 com sufixo Z (segundos)."""
    return momento.isoformat(timespec="seconds").replace("+00:00", "Z")


def novo_uuid_semeado(rng: random.Random) -> str:
    """UUID4 derivado do gerador semeado (determinístico)."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def montar_registro(
    rng: random.Random,
    fake: Faker,
    agora: datetime,
    tipos_permitidos: Sequence[TipoApontamento],
) -> dict:
    """Monta UM registro válido (estrutura aprovada pelos validadores)."""
    tipo = rng.choices(list(tipos_permitidos), weights=[PESOS_TIPO[t] for t in tipos_permitidos])[0]
    dados: dict = {
        "id_origem": novo_uuid_semeado(rng),
        "tipo": tipo.value,
        "data_hora": formatar_data_hora(agora - timedelta(seconds=rng.uniform(0, 86400))),
        "talhao_codigo": rng.choice(TALHOES_ATIVOS),
        "equipamento_codigo": None,
        "item_codigo": None,
        "peso_bruto": None,
        "peso_tara": None,
        "peso_liquido": None,
        "horas_maquina": None,
        "quantidade": None,
        "operador": fake.name(),
        "observacao": fake.sentence(nb_words=8) if rng.random() < 0.3 else None,
        "versao_contrato": VERSAO_CONTRATO,
    }
    if tipo == TipoApontamento.PESAGEM:
        # bruto 8.000–40.000; tara 1.500–12.000, sempre < bruto → líquido > 0.
        peso_bruto = round(rng.uniform(8000, 40000), 3)
        peso_tara = round(rng.uniform(1500, min(12000, peso_bruto - 0.001)), 3)
        dados.update(
            equipamento_codigo=rng.choice(EQUIPAMENTOS_ATIVOS),
            peso_bruto=peso_bruto,
            peso_tara=peso_tara,
            peso_liquido=round(peso_bruto - peso_tara, 3),
        )
    elif tipo == TipoApontamento.MAQUINA:
        dados.update(
            equipamento_codigo=rng.choice(EQUIPAMENTOS_ATIVOS),
            horas_maquina=round(rng.uniform(0.5, 14.0), 2),
        )
    else:  # INSUMO
        dados.update(
            item_codigo=rng.choice(ITENS_ATIVOS),
            quantidade=round(rng.uniform(10, 5000), 3),
        )
    # Valida aqui para garantir que o registro normal PASSA no contrato.
    return Apontamento.model_validate(dados).model_dump(mode="json")


def gerar_lote(
    quantidade: int,
    semente: int = 42,
    tipos: list[TipoApontamento] | None = None,
) -> list[dict]:
    """Gera `quantidade` registros válidos com a semente informada.

    Mesma semente + mesma quantidade → mesmos id_origem e valores (ver
    exceção de data_hora no docstring do módulo).
    """
    tipos_permitidos = list(tipos) if tipos else list(TipoApontamento)
    rng = random.Random(semente)
    fake = Faker("pt_BR")
    # Semente global (decisão do controller) + semente dedicada da instância,
    # que é a que efetivamente garante isolamento/reprodutibilidade por chamada.
    Faker.seed(semente)
    fake.seed_instance(semente)
    agora = datetime.now(timezone.utc)  # "agora" congelado no início da geração
    return [montar_registro(rng, fake, agora, tipos_permitidos) for _ in range(quantidade)]
