"""Pacote de rotas administrativas + helpers de serialização compartilhados."""
from datetime import datetime, timezone
from decimal import Decimal


def iso_z(valor: datetime | None) -> str | None:
    """Datetime do Oracle (naive, UTC) → ISO-8601 com sufixo Z."""
    if valor is None:
        return None
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.isoformat().replace("+00:00", "Z")


def numero(valor: object) -> object:
    """Decimal do Oracle → int/float serializável em JSON."""
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    return valor


def linha_para_dict(linha: tuple, descricao: tuple) -> dict:
    """Converte uma linha fetchada em dict com valores serializáveis."""
    resultado: dict = {}
    for coluna, valor in zip(descricao, linha):
        nome = coluna[0].lower()
        if isinstance(valor, datetime):
            resultado[nome] = iso_z(valor)
        elif isinstance(valor, Decimal):
            resultado[nome] = numero(valor)
        else:
            resultado[nome] = valor
    return resultado
