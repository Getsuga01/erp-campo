"""Catálogo de erros da integração — INT-001 a INT-099 (3.5).

Convenção de intervalos (decisão do controller): 012–049 reservado para
novas regras de negócio; 051–098 reservado para erros técnicos/infra.

A flag `recuperavel` indica se o registro pode ser reprocessado depois
(geralmente após correção de cadastro) com chance de êxito. Erros de
ciclo (INT-05x) são recuperáveis no sentido de que o PRÓXIMO ciclo pode
tentar de novo — eles não rejeitam registro individual.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Erro:
    """Definição imutável de um erro do catálogo."""

    codigo: str
    mensagem: str
    recuperavel: bool


CATALOGO: dict[str, Erro] = {
    "INT-001": Erro("INT-001", "campo obrigatório ausente", False),
    "INT-002": Erro("INT-002", "talhão inexistente no cadastro", True),
    "INT-003": Erro("INT-003", "talhão inativo no cadastro", True),
    "INT-004": Erro("INT-004", "equipamento inexistente ou inativo no cadastro", True),
    "INT-005": Erro("INT-005", "item inexistente no cadastro", True),
    "INT-006": Erro("INT-006", "peso líquido inválido (diferente de bruto - tara ou <= 0)", False),
    "INT-007": Erro("INT-007", "data_hora no futuro além da tolerância", False),
    "INT-008": Erro("INT-008", "horas_maquina fora do intervalo (0, 24]", False),
    "INT-009": Erro("INT-009", "versao_contrato não suportada", False),
    "INT-010": Erro("INT-010", "quantidade <= 0 em INSUMO", False),
    "INT-011": Erro("INT-011", "tipo desconhecido / payload não parseável", False),
    "INT-050": Erro("INT-050", "origem indisponível / timeout", True),
    "INT-051": Erro("INT-051", "erro 5xx da origem", True),
    "INT-052": Erro("INT-052", "banco Oracle indisponível", True),
    "INT-099": Erro("INT-099", "erro interno inesperado", False),
}


def obter_erro(codigo: str) -> Erro:
    """Retorna a definição do catálogo (KeyError se o código não existir)."""
    return CATALOGO[codigo]


class ErroRejeicao(Exception):
    """Rejeição de um registro individual (validação de contrato/negócio)."""

    def __init__(self, codigo: str, detalhe: str | None = None) -> None:
        base = obter_erro(codigo)
        self.codigo = codigo
        self.recuperavel = base.recuperavel
        self.mensagem = f"{base.mensagem}: {detalhe}" if detalhe else base.mensagem
        super().__init__(self.mensagem)


class ErroCiclo(Exception):
    """Falha de infraestrutura que aborta o ciclo inteiro (INT-05x/099)."""

    def __init__(self, codigo: str, detalhe: str | None = None) -> None:
        base = obter_erro(codigo)
        self.codigo = codigo
        self.mensagem = f"{base.mensagem}: {detalhe}" if detalhe else base.mensagem
        super().__init__(self.mensagem)
