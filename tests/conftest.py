"""Infraestrutura de testes da Fase 5 (tarefa 5.1).

Duas peças centrais:

1. **Loader de módulos com isolamento de nomes** — integrador e simulador
   usam imports absolutos top-level com colisão (`config`, `models`), então
   cada pacote é carregado num contexto controlado de sys.path/sys.modules;
   os módulos ficam registrados em `_MODULOS` e são acessados pelas fixtures
   `int_mod`/`sim_mod` (nunca `import models` direto nos testes).

2. **BancoFake** — Oracle em memória que reproduz a semântica das operações
   SQL usadas pelo integrador, com transações reais por snapshot/rollback
   (fidelidade ao commit por registro: INSERT não-commitado é revertido).
   Nenhum teste exige Oracle local (ruling R5 do ledger).

O helper `rodar_ciclo` substitui `ciclo.consumir_todas_paginas`; a regra 12
(test_resiliencia) usa o consumidor REAL com httpx MockTransport e backoff
sem sleep.
"""
import asyncio
import copy
import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import oracledb
import pytest

RAIZ_REPO = Path(__file__).resolve().parents[1]
DIR_INTEGRADOR = RAIZ_REPO / "integrador"
DIR_SIMULADOR = RAIZ_REPO / "simulador_campo"

NOME_CURSOR = "CAMPO_API"
SENTINELA = "1970-01-01T00:00:00Z"
CURSOR_FINAL_PADRAO = "2026-10-26T12:00:00Z"

# Módulos do integrador que fazem `from oracle_client import sessao/transacao`.
MODULOS_COM_ORACLE = (
    "validador",
    "idempotencia",
    "cursor",
    "lote",
    "gravador",
    "rejeitador",
    "reprocessador",
)


# ---------------------------------------------------------------------------
# Loader de módulos com isolamento de nomes
# ---------------------------------------------------------------------------

_MODULOS: dict[tuple[str, str], ModuleType] = {}
_DIRETORIOS = {"integrador": DIR_INTEGRADOR, "simulador_campo": DIR_SIMULADOR}


def _nomes_do_pacote(diretorio: Path) -> set[str]:
    nomes = {arquivo.stem for arquivo in diretorio.glob("*.py") if arquivo.stem != "__init__"}
    if (diretorio / "rotas").is_dir():
        nomes.add("rotas")
    return nomes


@contextmanager
def _contexto_de_carga(diretorio: Path) -> Iterator[set[str]]:
    """Carrega módulos do diretório isolando sys.path e sys.modules."""
    nomes = _nomes_do_pacote(diretorio)
    salvos: dict[str, ModuleType] = {}
    for nome in nomes:
        for chave in [k for k in list(sys.modules) if k == nome or k.startswith(nome + ".")]:
            salvos[chave] = sys.modules.pop(chave)
    sys.path.insert(0, str(diretorio))
    try:
        yield nomes
    finally:
        sys.path.remove(str(diretorio))
        for nome in nomes:
            for chave in [k for k in list(sys.modules) if k == nome or k.startswith(nome + ".")]:
                modulo_carregado = sys.modules.pop(chave)
                if isinstance(modulo_carregado, ModuleType):
                    _MODULOS.setdefault((diretorio.name, chave), modulo_carregado)
        for chave, modulo_salvo in salvos.items():
            sys.modules[chave] = modulo_salvo


def modulo(pacote: str, nome: str) -> ModuleType:
    """Retorna o módulo `nome` do pacote, carregando-o na primeira vez.

    O pacote INTEIRO é carregado num único contexto na primeira solicitação:
    carregar módulos isoladamente re-executaria as dependências comuns
    (config/models/cursor...) criando instâncias duplicadas — os patches de
    teste aplicariam-se a uma instância enquanto o código sob teste usaria
    outra (instâncias sem patch falariam de verdade contra um Oracle local).
    """
    if not any(carga[0] == pacote for carga in _MODULOS):
        diretorio = _DIRETORIOS[pacote]
        with _contexto_de_carga(diretorio):
            for nome_modulo in sorted(_nomes_do_pacote(diretorio) - {"rotas"}):
                try:
                    importlib.import_module(nome_modulo)
                except ImportError:
                    # Dependência opcional ausente (ex.: APScheduler) — o
                    # módulo fica simplesmente indisponível para os testes.
                    pass
    try:
        return _MODULOS[(pacote, nome)]
    except KeyError:
        raise AssertionError(f"módulo {nome!r} indisponível no pacote {pacote!r}") from None


@pytest.fixture(scope="session")
def int_mod():
    """Acesso aos módulos do integrador: `int_mod("ciclo")`."""
    return lambda nome: modulo("integrador", nome)


@pytest.fixture(scope="session")
def sim_mod():
    """Acesso aos módulos do simulador: `sim_mod("gerador")`."""
    return lambda nome: modulo("simulador_campo", nome)


# ---------------------------------------------------------------------------
# BancoFake — Oracle em memória
# ---------------------------------------------------------------------------


@dataclass
class LoteFake:
    id: int
    status: str
    cursor_inicio: str | None = None
    cursor_fim: str | None = None
    total_recebidos: int | None = None
    total_gravados: int | None = None
    total_rejeitados: int | None = None
    total_duplicados: int | None = None
    observacao: str | None = None
    iniciado_em: datetime | None = None
    fechado_em: datetime | None = None


@dataclass
class RegistroFake:
    id: int
    lote_id: int
    id_origem: str
    tipo: str
    status: str
    payload_original: str
    origem: str = "CICLO"
    codigo_erro: str | None = None
    mensagem_erro: str | None = None
    recebido_em: datetime | None = None
    processado_em: datetime | None = None


@dataclass
class ApontamentoFake:
    registro_id: int
    id_origem: str
    tipo: str
    data_hora: object
    talhao_id: int
    equipamento_id: int | None
    item_id: int | None
    peso_bruto: float | None
    peso_tara: float | None
    peso_liquido: float | None
    horas_maquina: float | None
    quantidade: float | None
    operador: str
    observacao: str | None


@dataclass
class ItemFilaFake:
    id: int
    registro_id: int
    situacao: str
    tentativas: int
    max_tentativas: int
    proxima_tentativa: datetime
    motivo: str | None
    criado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    atualizado_em: datetime | None = None


@dataclass
class TentativaFake:
    id: int
    fila_id: int
    numero_tentativa: int
    resultado: str
    codigo_erro: str | None = None
    acionado_por: str = "SISTEMA"
    observacao: str | None = None


class VarFake:
    """Mímica de oracledb.Var para RETURNING INTO (getvalue devolve lista)."""

    def __init__(self) -> None:
        self._valor: list = [None]

    def preencher(self, valor) -> None:
        self._valor = [valor]

    def getvalue(self):
        return self._valor

    def setvalue(self, posicao: int, valor) -> None:
        self._valor = [valor]


class CursorFake:
    """Cursor que casa cada SQL do integrador com um handler do BancoFake."""

    def __init__(self, banco: "BancoFake") -> None:
        self._banco = banco
        self.rowcount = -1
        self._linhas: list = []

    def var(self, tipo) -> VarFake:
        return VarFake()

    def execute(self, sql: str, params: dict | None = None) -> "CursorFake":
        self._linhas = []
        self._banco._cursor_atual = self
        normalizada = " ".join(sql.split()).upper()
        self.rowcount = self._banco.executar(normalizada, params or {})
        return self

    def fetchone(self):
        return self._linhas[0] if self._linhas else None

    def fetchall(self):
        return self._linhas


class ConexaoFake:
    def __init__(self, banco: "BancoFake") -> None:
        self._banco = banco

    def cursor(self) -> CursorFake:
        return CursorFake(self._banco)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


class BancoFake:
    """Oracle em memória com transações por snapshot/rollback.

    Cada statement é casado por assinatura (SQL normalizada em maiúsculas);
    mutações aplicam imediatamente, mas `transacao()` restaura o snapshot em
    exceção (equivalente ao rollback real) e `sessao()` restaura ao sair
    (leitura pura, rollback implícito do pool).
    """

    def __init__(self) -> None:
        self.cursors: dict[str, str] = {}
        self.lotes: list[LoteFake] = []
        self.registros: list[RegistroFake] = []
        self.apontamentos: list[ApontamentoFake] = []
        self.fila: list[ItemFilaFake] = []
        self.tentativas: list[TentativaFake] = []
        self._seq = {"lote": 0, "registro": 0, "apontamento": 0, "fila": 0, "tentativa": 0}
        self.talhoes: dict[str, tuple[int, int]] = {}
        self.equipamentos: dict[str, tuple[int, int]] = {}
        self.itens: dict[str, tuple[int]] = {}
        # Gancho de teste: faz o N-ésimo INSERT de apontamento falhar (crash).
        self.falhar_apontamento_em: int | None = None

    # -- seed de cadastros (domínio de db/07_carga_mestres.sql) -------------

    def semear_cadastros(self) -> None:
        for indice in range(1, 19):
            self.talhoes[f"TAL-{indice:03d}"] = (indice, 1)
        self.talhoes["TAL-019"] = (19, 0)
        self.talhoes["TAL-020"] = (20, 0)
        for indice in range(1, 15):
            self.equipamentos[f"EQP-{indice:03d}"] = (indice, 1)
        self.equipamentos["EQP-015"] = (15, 0)
        for indice in range(1, 11):
            self.itens[f"ITEM-{indice:03d}"] = (indice,)

    def cadastrar_talhao(self, codigo: str, ativo: int = 1) -> None:
        self.talhoes[codigo] = (max(v[0] for v in self.talhoes.values()) + 1, ativo)

    def expirar_fila(self) -> None:
        """Torna todos os itens da fila elegíveis (proxima_tentativa vencida)."""
        passado = datetime.now(timezone.utc) - timedelta(hours=1)
        for item in self.fila:
            item.proxima_tentativa = passado

    # -- contextos de conexão ------------------------------------------------

    def _snapshot(self) -> dict:
        return {
            "cursors": copy.deepcopy(self.cursors),
            "lotes": copy.deepcopy(self.lotes),
            "registros": copy.deepcopy(self.registros),
            "apontamentos": copy.deepcopy(self.apontamentos),
            "fila": copy.deepcopy(self.fila),
            "tentativas": copy.deepcopy(self.tentativas),
            "seq": dict(self._seq),
            "talhoes": copy.deepcopy(self.talhoes),
            "equipamentos": copy.deepcopy(self.equipamentos),
            "itens": copy.deepcopy(self.itens),
        }

    def _restaurar(self, foto: dict) -> None:
        for campo, valor in foto.items():
            setattr(self, campo, valor)

    @contextmanager
    def transacao(self) -> Iterator[ConexaoFake]:
        foto = self._snapshot()
        try:
            yield ConexaoFake(self)
        except Exception:
            self._restaurar(foto)
            raise

    @contextmanager
    def sessao(self) -> Iterator[ConexaoFake]:
        foto = self._snapshot()
        try:
            yield ConexaoFake(self)
        finally:
            self._restaurar(foto)

    # -- dispatcher de SQL ----------------------------------------------------

    def executar(self, s: str, p: dict) -> int:
        """Executa a statement casando a assinatura; devolve rowcount."""
        assert self._cursor_atual is not None, "execute chamado fora de cursor"
        cur = self._cursor_atual

        def responder(linhas: list, rowcount: int = 0) -> int:
            cur._linhas = linhas
            return rowcount

        if "SELECT POSICAO FROM INT_CURSOR" in s:
            posicao = self.cursors.get(p["nome"])
            return responder([(posicao,)] if posicao is not None else [])

        if "INSERT INTO INT_CURSOR" in s:
            self.cursors[p["nome"]] = p["posicao"]
            return responder([])

        if "UPDATE INT_CURSOR" in s:
            if p["nome"] not in self.cursors:
                return responder([], rowcount=0)
            self.cursors[p["nome"]] = p["posicao"]
            return responder([], rowcount=1)

        if "INSERT INTO INT_LOTE" in s:
            self._seq["lote"] += 1
            lote = LoteFake(
                id=self._seq["lote"],
                status=p["status"],
                cursor_inicio=p["cursor_inicio"],
                iniciado_em=datetime.now(timezone.utc),
            )
            self.lotes.append(lote)
            p["id"].preencher(lote.id)
            return responder([])

        if "SELECT SUM(CASE WHEN STATUS = 'GRAVADO'" in s:
            do_lote = [r for r in self.registros if r.lote_id == p["lote"]]
            gravados = sum(1 for r in do_lote if r.status == "GRAVADO")
            rejeitados = sum(1 for r in do_lote if r.status == "REJEITADO")
            return responder([(gravados, rejeitados)])

        if "UPDATE INT_LOTE" in s:
            for lote in self.lotes:
                if lote.id == p["lote"]:
                    lote.status = p["status"]
                    lote.total_recebidos = p["recebidos"]
                    lote.total_gravados = p["gravados"]
                    lote.total_rejeitados = p["rejeitados"]
                    lote.total_duplicados = p["duplicados"]
                    lote.cursor_fim = p["cursor_fim"]
                    lote.observacao = p["observacao"]
                    lote.fechado_em = datetime.now(timezone.utc)
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        if "SELECT STATUS FROM INT_REGISTRO WHERE ID_ORIGEM" in s:
            registro = next((r for r in self.registros if r.id_origem == p["id_origem"]), None)
            return responder([(registro.status,)] if registro else [])

        if "SELECT ID, ATIVO FROM TALHAO" in s:
            talhao = self.talhoes.get(p["codigo"])
            return responder([talhao] if talhao else [])

        if "SELECT ID, ATIVO FROM EQUIPAMENTO" in s:
            equipamento = self.equipamentos.get(p["codigo"])
            return responder([equipamento] if equipamento else [])

        if "SELECT ID FROM ERP_SUPRIMENTOS.ITEM" in s:
            item = self.itens.get(p["codigo"])
            return responder([item] if item else [])

        if "INSERT INTO INT_REGISTRO" in s:
            if any(r.id_origem == p["id_origem"] for r in self.registros):
                raise oracledb.IntegrityError(f"UK violada: id_origem {p['id_origem']}")
            self._seq["registro"] += 1
            if "CODIGO_ERRO" in s:  # rejeitador
                registro = RegistroFake(
                    id=self._seq["registro"],
                    lote_id=p["lote_id"],
                    id_origem=p["id_origem"],
                    tipo=p["tipo"],
                    status="REJEITADO",
                    codigo_erro=p["codigo_erro"],
                    mensagem_erro=p["mensagem"],
                    payload_original=p["payload"],
                    recebido_em=datetime.now(timezone.utc),
                )
            else:  # gravador
                registro = RegistroFake(
                    id=self._seq["registro"],
                    lote_id=p["lote_id"],
                    id_origem=p["id_origem"],
                    tipo=p["tipo"],
                    status="RECEBIDO",
                    payload_original=p["payload"],
                    recebido_em=datetime.now(timezone.utc),
                )
            self.registros.append(registro)
            p["registro_id"].preencher(registro.id)
            return responder([])

        if "INSERT INTO ERP_SUPRIMENTOS.APONTAMENTO_CAMPO" in s:
            if self.falhar_apontamento_em is not None:
                if len(self.apontamentos) + 1 == self.falhar_apontamento_em:
                    raise oracledb.DatabaseError("crash simulado no INSERT do apontamento")
            if any(a.registro_id == p["registro_id"] for a in self.apontamentos):
                raise oracledb.IntegrityError(f"UK violada: registro_id {p['registro_id']}")
            self.apontamentos.append(
                ApontamentoFake(
                    registro_id=p["registro_id"],
                    id_origem=p["id_origem"],
                    tipo=p["tipo"],
                    data_hora=p["data_hora"],
                    talhao_id=p["talhao_id"],
                    equipamento_id=p["equipamento_id"],
                    item_id=p["item_id"],
                    peso_bruto=p["peso_bruto"],
                    peso_tara=p["peso_tara"],
                    peso_liquido=p["peso_liquido"],
                    horas_maquina=p["horas_maquina"],
                    quantidade=p["quantidade"],
                    operador=p["operador"],
                    observacao=p["observacao"],
                )
            )
            return responder([])

        if "UPDATE INT_REGISTRO SET STATUS = 'GRAVADO', CODIGO_ERRO = NULL" in s:
            for registro in self.registros:
                if registro.id == p["registro_id"]:
                    registro.status = "GRAVADO"
                    registro.codigo_erro = None
                    registro.mensagem_erro = None
                    registro.processado_em = datetime.now(timezone.utc)
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        if "UPDATE INT_REGISTRO SET STATUS = 'GRAVADO'" in s:
            for registro in self.registros:
                if registro.id == p["registro_id"]:
                    registro.status = "GRAVADO"
                    registro.processado_em = datetime.now(timezone.utc)
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        if "UPDATE INT_REGISTRO SET CODIGO_ERRO" in s:
            for registro in self.registros:
                if registro.id == p["registro_id"]:
                    registro.codigo_erro = p["codigo"]
                    registro.mensagem_erro = p["mensagem"]
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        if "INSERT INTO FILA_REPROCESSAMENTO" in s:
            self._seq["fila"] += 1
            item = ItemFilaFake(
                id=self._seq["fila"],
                registro_id=p["registro_id"],
                situacao="PENDENTE",
                tentativas=0,
                max_tentativas=p["max_tentativas"],
                proxima_tentativa=datetime.now(timezone.utc) + timedelta(minutes=p["intervalo"]),
                motivo=p["motivo"],
            )
            self.fila.append(item)
            p["fila_id"].preencher(item.id)
            return responder([])

        if "FOR UPDATE SKIP LOCKED" in s:
            agora = datetime.now(timezone.utc)
            for item in self.fila:
                if item.situacao == "PENDENTE" and item.proxima_tentativa <= agora:
                    return responder([(item.id, item.registro_id)])
            return responder([])

        if "SET SITUACAO = 'PROCESSANDO'" in s:
            for item in self.fila:
                if item.id == p["fila_id"]:
                    item.situacao = "PROCESSANDO"
                    item.atualizado_em = datetime.now(timezone.utc)
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        if "SELECT ID, STATUS FROM INT_REGISTRO" in s:
            registro = next((r for r in self.registros if r.id == p["registro_id"]), None)
            return responder([(registro.id, registro.status)] if registro else [])

        if "SELECT ID, SITUACAO FROM FILA_REPROCESSAMENTO" in s:
            item = next((f for f in self.fila if f.registro_id == p["registro_id"]), None)
            return responder([(item.id, item.situacao)] if item else [])

        if "TENTATIVAS = CASE WHEN" in s:
            for item in self.fila:
                if item.id == p["fila_id"] and item.situacao in ("PENDENTE", "DEAD_LETTER"):
                    item.situacao = "PENDENTE"
                    if p["resetar"] == 1:
                        item.tentativas = 0
                    item.proxima_tentativa = datetime.now(timezone.utc)
                    item.atualizado_em = datetime.now(timezone.utc)
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        if "JOIN INT_REGISTRO R" in s:
            item = next((f for f in self.fila if f.id == p["fila_id"]), None)
            if item is None:
                return responder([])
            registro = next((r for r in self.registros if r.id == item.registro_id), None)
            if registro is None:
                return responder([])
            return responder(
                [(
                    item.tentativas,
                    item.max_tentativas,
                    registro.status,
                    registro.id_origem,
                    registro.payload_original,
                )]
            )

        if "SET SITUACAO = 'CONCLUIDA'" in s:
            for item in self.fila:
                if item.id == p["fila_id"]:
                    item.situacao = "CONCLUIDA"
                    item.atualizado_em = datetime.now(timezone.utc)
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        if "INSERT INTO INT_TENTATIVA" in s:
            self._seq["tentativa"] += 1
            resultado = "SUCESSO" if "'SUCESSO'" in s else "FALHA"
            self.tentativas.append(
                TentativaFake(
                    id=self._seq["tentativa"],
                    fila_id=p["fila_id"],
                    numero_tentativa=p["numero"],
                    resultado=resultado,
                    codigo_erro=p.get("codigo"),
                    acionado_por=p["acionado_por"],
                    observacao=p["observacao"],
                )
            )
            return responder([])

        if "UPDATE FILA_REPROCESSAMENTO SET TENTATIVAS = :NOVA" in s:
            for item in self.fila:
                if item.id == p["fila_id"]:
                    item.tentativas = p["nova"]
                    item.situacao = p["situacao"]
                    item.proxima_tentativa = datetime.now(timezone.utc) + timedelta(
                        minutes=p["intervalo"]
                    )
                    item.atualizado_em = datetime.now(timezone.utc)
                    return responder([], rowcount=1)
            return responder([], rowcount=0)

        raise AssertionError(f"SQL não reconhecida pelo BancoFake: {s!r}")

    _cursor_atual: "CursorFake | None" = None


# ---------------------------------------------------------------------------
# Fábrica de payloads do contrato v1.0
# ---------------------------------------------------------------------------


def _agora_iso_passado() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class FabricaPayloads:
    """Gera payloads válidos por tipo, com overrides por teste."""

    def __init__(self) -> None:
        self._sequencia = 0

    def novo_id(self) -> str:
        self._sequencia += 1
        return f"00000000-0000-4000-8000-{self._sequencia:012d}"

    def pesagem(self, id_origem: str | None = None, **overrides) -> dict:
        payload = {
            "id_origem": id_origem or self.novo_id(),
            "tipo": "PESAGEM",
            "data_hora": _agora_iso_passado(),
            "talhao_codigo": "TAL-001",
            "equipamento_codigo": "EQP-001",
            "item_codigo": None,
            "peso_bruto": 10000.0,
            "peso_tara": 3000.0,
            "peso_liquido": 7000.0,
            "horas_maquina": None,
            "quantidade": None,
            "operador": "Operador Teste",
            "observacao": None,
            "versao_contrato": "1.0",
        }
        payload.update(overrides)
        return payload

    def maquina(self, id_origem: str | None = None, **overrides) -> dict:
        payload = {
            "id_origem": id_origem or self.novo_id(),
            "tipo": "MAQUINA",
            "data_hora": _agora_iso_passado(),
            "talhao_codigo": "TAL-002",
            "equipamento_codigo": "EQP-002",
            "item_codigo": None,
            "peso_bruto": None,
            "peso_tara": None,
            "peso_liquido": None,
            "horas_maquina": 8.0,
            "quantidade": None,
            "operador": "Operador Teste",
            "observacao": None,
            "versao_contrato": "1.0",
        }
        payload.update(overrides)
        return payload

    def insumo(self, id_origem: str | None = None, **overrides) -> dict:
        payload = {
            "id_origem": id_origem or self.novo_id(),
            "tipo": "INSUMO",
            "data_hora": _agora_iso_passado(),
            "talhao_codigo": "TAL-003",
            "equipamento_codigo": None,
            "item_codigo": "ITEM-001",
            "peso_bruto": None,
            "peso_tara": None,
            "peso_liquido": None,
            "horas_maquina": None,
            "quantidade": 500.0,
            "operador": "Operador Teste",
            "observacao": None,
            "versao_contrato": "1.0",
        }
        payload.update(overrides)
        return payload


# ---------------------------------------------------------------------------
# Fixtures e helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def banco() -> BancoFake:
    """BancoFake com cadastros mestres semeados (domínio do db/07)."""
    instancia = BancoFake()
    instancia.semear_cadastros()
    return instancia


@pytest.fixture
def oracle(banco: BancoFake, monkeypatch, int_mod) -> BancoFake:
    """Troca sessao/transacao do oracle_client por BancoFake em todos os módulos."""
    for nome in MODULOS_COM_ORACLE:
        modulo_alvo = int_mod(nome)
        if hasattr(modulo_alvo, "sessao"):
            monkeypatch.setattr(modulo_alvo, "sessao", banco.sessao)
        if hasattr(modulo_alvo, "transacao"):
            monkeypatch.setattr(modulo_alvo, "transacao", banco.transacao)
    return banco


@pytest.fixture(scope="session")
def payloads() -> FabricaPayloads:
    return FabricaPayloads()


@pytest.fixture(autouse=True)
def _proibir_oracle_real(int_mod, monkeypatch):
    """Trava de segurança: nenhum teste pode tocar o Oracle real.

    Se algum módulo não patchado escapar ao BancoFake e tentar criar o pool
    real, o teste falha alto em vez de ler/escrever no banco de desenvolvimento
    (incidente registrado no report da task 5).
    """
    oracle_client = int_mod("oracle_client")

    def _negado(*args, **kwargs):
        raise AssertionError(
            "teste tentou usar o pool Oracle real — todo acesso a banco deve "
            "passar pelo BancoFake (fixture `oracle`)"
        )

    monkeypatch.setattr(oracle_client, "obter_pool", _negado)
    monkeypatch.setattr(oracle_client, "iniciar_pool", _negado)


def rodar_ciclo(int_mod, monkeypatch, itens: list[dict], cursor_final: str = CURSOR_FINAL_PADRAO):
    """Executa um ciclo com consumidor fake retornando `itens` (regra 1–3, 10)."""
    ciclo = int_mod("ciclo")

    async def _consumir_fake(cursor_atual):
        return list(itens), cursor_final

    monkeypatch.setattr(ciclo, "consumir_todas_paginas", _consumir_fake)
    return asyncio.run(ciclo.executar_ciclo())
