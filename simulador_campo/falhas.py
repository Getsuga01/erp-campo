"""Injeção controlada de falhas — gera registros que VIOLAM as regras.

Cada tipo de falha produz um registro inválido persistido normalmente no
SQLite (o simulador serve tudo; quem rejeita é o integrador). Onde aplicável,
os demais campos seguem usando códigos de mestre reais, para isolar exatamente
a regra violada.
"""
import random
from datetime import datetime, timedelta, timezone

from faker import Faker

from gerador import formatar_data_hora, montar_registro
from models import TipoApontamento, TipoFalha
from persistencia import inserir_varios, sortear_registro_existente


def _montar_base(rng: random.Random, fake: Faker, agora: datetime, tipos: list[TipoApontamento]) -> dict:
    """Registro válido de partida, que a falha altera em seguida."""
    return montar_registro(rng, fake, agora, tipos)


def injetar(tipo_falha: TipoFalha, quantidade: int) -> list[str]:
    """Cria e persiste `quantidade` registros com a violação pedida.

    Retorna os id_origem gerados (na DUPLICATA, um por linha criada — um par
    na base vazia gera duas linhas com o mesmo UUID).
    """
    rng = random.Random()  # falhas não exigem reprodutibilidade
    fake = Faker("pt_BR")
    agora = datetime.now(timezone.utc)
    itens: list[tuple[dict, bool]] = []  # (payload, duplicado)
    ids: list[str] = []

    if tipo_falha == TipoFalha.DUPLICATA:
        base_vazia = sortear_registro_existente() is None
        for _ in range(quantidade):
            if base_vazia:
                # Sem registros: gera um par (duas linhas com o MESMO UUID).
                par = _montar_base(rng, fake, agora, list(TipoApontamento))
                itens.append((par, False))
                itens.append((par, True))
                ids.extend([par["id_origem"], par["id_origem"]])
            else:
                # Reinsere um registro existente com o mesmo id_origem.
                original = sortear_registro_existente()
                itens.append((original, True))
                ids.append(original["id_origem"])
    else:
        for _ in range(quantidade):
            if tipo_falha == TipoFalha.TALHAO_INEXISTENTE:
                payload = _montar_base(rng, fake, agora, list(TipoApontamento))
                payload["talhao_codigo"] = "TAL-999"
            elif tipo_falha == TipoFalha.PESO_NEGATIVO:
                payload = _montar_base(rng, fake, agora, [TipoApontamento.PESAGEM])
                payload["peso_tara"] = round(payload["peso_bruto"] + rng.uniform(500, 5000), 3)
                payload["peso_liquido"] = round(payload["peso_bruto"] - payload["peso_tara"], 3)
            elif tipo_falha == TipoFalha.DATA_FUTURA:
                payload = _montar_base(rng, fake, agora, list(TipoApontamento))
                payload["data_hora"] = formatar_data_hora(agora + timedelta(hours=2))
            elif tipo_falha == TipoFalha.CAMPO_AUSENTE:
                payload = _montar_base(rng, fake, agora, list(TipoApontamento))
                payload.pop("talhao_codigo")  # campo removido, não nulo
            elif tipo_falha == TipoFalha.ITEM_INEXISTENTE:
                payload = _montar_base(rng, fake, agora, [TipoApontamento.INSUMO])
                payload["item_codigo"] = "ITEM-999"
            else:  # HORAS_INVALIDAS
                payload = _montar_base(rng, fake, agora, [TipoApontamento.MAQUINA])
                payload["horas_maquina"] = 25.0
            itens.append((payload, False))
            ids.append(payload["id_origem"])

    inserir_varios(itens)
    return ids
