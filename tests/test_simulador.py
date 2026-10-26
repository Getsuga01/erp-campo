"""Testes do simulador do sistema de campo (tarefa 5.9).

Cobertura: reprodutibilidade por semente (com data_hora congelada — exceção
documentada do gerador), injeção controlada de falhas (cada tipo viola
exatamente a regra alvo), persistência SQLite entre "reinícios", UK de
id_origem, contrato de paginação R9 e endpoints da API (auth X-API-Key,
health, gerar, injetar-falha, modo-indisponível).
"""
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

CHAVE = {"X-API-Key": "campo-dev-key-001"}


@pytest.fixture
def db_sim(sim_mod, monkeypatch, tmp_path):
    """SQLite temporário por teste + settings recarregadas."""
    monkeypatch.setenv("CAMPO_DB_PATH", str(tmp_path / "simulador_teste.db"))
    config = sim_mod("config")
    config.obter_settings.cache_clear()
    sim_mod("database").iniciar_banco()
    yield sim_mod
    config.obter_settings.cache_clear()


@pytest.fixture
def cliente_sim(sim_mod, monkeypatch, tmp_path):
    """TestClient com lifespan (banco temporário e estado limpo)."""
    monkeypatch.setenv("CAMPO_DB_PATH", str(tmp_path / "simulador_teste.db"))
    config = sim_mod("config")
    config.obter_settings.cache_clear()
    main = sim_mod("main")
    with TestClient(main.app) as client:
        yield client
    config.obter_settings.cache_clear()


# -- reprodutibilidade do gerador ---------------------------------------------


def test_mesma_semente_gera_registros_identicos(sim_mod, monkeypatch):
    gerador = sim_mod("gerador")
    congelado = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)

    class DatetimeCongelado(datetime):
        @classmethod
        def now(cls, tz=None):
            return congelado

    monkeypatch.setattr(gerador, "datetime", DatetimeCongelado)
    lote1 = gerador.gerar_lote(25, semente=42)
    lote2 = gerador.gerar_lote(25, semente=42)
    assert lote1 == lote2  # id_origem, valores E data_hora (agora congelado)


def test_reprodutibilidade_do_mundo_real_mesmos_ids_e_valores(sim_mod):
    """Sem congelar o relógio: id_origem e valores se repetem (data_hora não)."""
    gerador = sim_mod("gerador")
    lote1 = gerador.gerar_lote(20, semente=7)
    lote2 = gerador.gerar_lote(20, semente=7)
    assert [r["id_origem"] for r in lote1] == [r["id_origem"] for r in lote2]
    for r1, r2 in zip(lote1, lote2):
        assert {k: v for k, v in r1.items() if k != "data_hora"} == {
            k: v for k, v in r2.items() if k != "data_hora"
        }


def test_sementes_diferentes_geram_registros_diferentes(sim_mod):
    gerador = sim_mod("gerador")
    lote_a = gerador.gerar_lote(10, semente=1)
    lote_b = gerador.gerar_lote(10, semente=2)
    assert {r["id_origem"] for r in lote_a}.isdisjoint({r["id_origem"] for r in lote_b})


def test_gerador_respeita_tipos_restritos_e_produz_validos(sim_mod):
    gerador = sim_mod("gerador")
    modelos = sim_mod("models")
    so_pesagem = gerador.gerar_lote(15, semente=3, tipos=[modelos.TipoApontamento.PESAGEM])
    assert len(so_pesagem) == 15
    assert all(r["tipo"] == "PESAGEM" for r in so_pesagem)
    # Registros normais passam na validação estrutural do contrato
    for registro in gerador.gerar_lote(30, semente=4):
        modelos.Apontamento.model_validate(registro)
    # Códigos de mestre sempre dentro do domínio ativo
    assert all(r["talhao_codigo"].startswith("TAL-0") for r in so_pesagem)
    assert all(r["equipamento_codigo"].startswith("EQP-0") for r in so_pesagem)


# -- injeção de falhas ---------------------------------------------------------


def test_falha_talhao_inexistente(db_sim):
    falhas, persistencia = db_sim("falhas"), db_sim("persistencia")
    (id_origem,) = falhas.injetar(db_sim("models").TipoFalha.TALHAO_INEXISTENTE, 1)
    assert persistencia.buscar_por_id_origem(id_origem)["talhao_codigo"] == "TAL-999"


def test_falha_peso_negativo(db_sim):
    falhas, persistencia = db_sim("falhas"), db_sim("persistencia")
    (id_origem,) = falhas.injetar(db_sim("models").TipoFalha.PESO_NEGATIVO, 1)
    payload = persistencia.buscar_por_id_origem(id_origem)
    assert payload["peso_liquido"] < 0
    assert payload["peso_tara"] > payload["peso_bruto"]


def test_falha_data_futura(db_sim):
    falhas, persistencia = db_sim("falhas"), db_sim("persistencia")
    (id_origem,) = falhas.injetar(db_sim("models").TipoFalha.DATA_FUTURA, 1)
    payload = persistencia.buscar_por_id_origem(id_origem)
    momento = datetime.fromisoformat(payload["data_hora"].replace("Z", "+00:00"))
    assert momento > datetime.now(timezone.utc) + timedelta(minutes=30)


def test_falha_campo_ausente(db_sim):
    falhas, persistencia = db_sim("falhas"), db_sim("persistencia")
    (id_origem,) = falhas.injetar(db_sim("models").TipoFalha.CAMPO_AUSENTE, 1)
    payload = persistencia.buscar_por_id_origem(id_origem)
    assert "talhao_codigo" not in payload  # removido, não nulo


def test_falha_item_inexistente(db_sim):
    falhas, persistencia = db_sim("falhas"), db_sim("persistencia")
    (id_origem,) = falhas.injetar(db_sim("models").TipoFalha.ITEM_INEXISTENTE, 1)
    payload = persistencia.buscar_por_id_origem(id_origem)
    assert payload["tipo"] == "INSUMO"
    assert payload["item_codigo"] == "ITEM-999"


def test_falha_horas_invalidas(db_sim):
    falhas, persistencia = db_sim("falhas"), db_sim("persistencia")
    (id_origem,) = falhas.injetar(db_sim("models").TipoFalha.HORAS_INVALIDAS, 1)
    payload = persistencia.buscar_por_id_origem(id_origem)
    assert payload["tipo"] == "MAQUINA"
    assert payload["horas_maquina"] == 25.0


def test_falha_duplicata_em_base_vazia_gera_par(db_sim):
    falhas, persistencia = db_sim("falhas"), db_sim("persistencia")
    ids = falhas.injetar(db_sim("models").TipoFalha.DUPLICATA, 1)
    assert len(ids) == 2 and ids[0] == ids[1]  # um par com o MESMO UUID
    assert persistencia.contar_apontamentos() == 2


def test_falha_duplicata_reinsere_registro_existente(db_sim):
    gerador, persistencia = db_sim("gerador"), db_sim("persistencia")
    originais = gerador.gerar_lote(3, semente=42)
    persistencia.inserir_varios([(r, False) for r in originais])
    ids = db_sim("falhas").injetar(db_sim("models").TipoFalha.DUPLICATA, 2)
    assert len(ids) == 2
    assert persistencia.contar_apontamentos() == 5
    for id_origem in ids:
        assert persistencia.buscar_por_id_origem(id_origem)["id_origem"] == id_origem


# -- persistência e paginação ---------------------------------------------------


def test_uk_de_id_origem_rejeita_reinsercao(db_sim):
    gerador, persistencia = db_sim("gerador"), db_sim("persistencia")
    registro = gerador.gerar_lote(1, semente=42)[0]
    persistencia.inserir_varios([(registro, False)])
    with pytest.raises(sqlite3.IntegrityError):
        persistencia.inserir_varios([(registro, False)])


def test_dados_sobrevivem_a_reinicio_do_banco(db_sim):
    gerador, persistencia, database = db_sim("gerador"), db_sim("persistencia"), db_sim("database")
    registros = gerador.gerar_lote(4, semente=42)
    persistencia.inserir_varios([(r, False) for r in registros])
    id_primeiro = registros[0]["id_origem"]

    database.iniciar_banco()  # "reinício": DDL idempotente sobre o mesmo arquivo
    assert persistencia.contar_apontamentos() == 4
    assert persistencia.buscar_por_id_origem(id_primeiro)["id_origem"] == id_primeiro


def test_paginacao_por_cursor_com_ordem_estavel(db_sim):
    gerador, persistencia = db_sim("gerador"), db_sim("persistencia")
    registros = gerador.gerar_lote(5, semente=42)
    persistencia.inserir_varios([(r, False) for r in registros])

    pagina1, cursor1 = persistencia.listar_paginado(None, 2)
    pagina2, cursor2 = persistencia.listar_paginado(cursor1, 2)
    pagina3, cursor3 = persistencia.listar_paginado(cursor2, 2)
    vazia, cursor_nulo = persistencia.listar_paginado(cursor3, 2)

    assert [r["id_origem"] for r in pagina1 + pagina2 + pagina3] == [
        r["id_origem"] for r in registros
    ]
    assert len(pagina3) == 1  # página parcial encerra a paginação (R9)
    assert cursor_nulo is None  # null SOMENTE em página vazia
    assert vazia == []


# -- API (endpoints) -------------------------------------------------------------


def test_health_sem_api_key(cliente_sim):
    resposta = cliente_sim.get("/health")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert corpo["total_apontamentos"] == 0
    assert corpo["modo_indisponivel_ate"] is None


def test_endpoints_exigem_api_key(cliente_sim):
    sem_key = cliente_sim.get("/apontamentos")
    assert sem_key.status_code == 401
    key_invalida = cliente_sim.get("/apontamentos", headers={"X-API-Key": "errada"})
    assert key_invalida.status_code == 401


def test_gerar_listar_e_buscar_por_id(cliente_sim):
    gerar = cliente_sim.post("/simulador/gerar", json={"quantidade": 5, "semente": 42}, headers=CHAVE)
    assert gerar.status_code == 200
    ids = gerar.json()["ids_origem"]
    assert len(ids) == 5

    listagem = cliente_sim.get("/apontamentos", headers=CHAVE).json()
    assert len(listagem["itens"]) == 5
    assert listagem["proximo_cursor"] is not None

    achado = cliente_sim.get(f"/apontamentos/{ids[0]}", headers=CHAVE)
    assert achado.status_code == 200
    assert achado.json()["id_origem"] == ids[0]

    ausente = cliente_sim.get("/apontamentos/00000000-0000-4000-8000-999999999999", headers=CHAVE)
    assert ausente.status_code == 404
    assert ausente.json() == {"detalhe": "apontamento nao encontrado"}


def test_gerar_mesma_semente_sem_limpar_a_base_da_409(cliente_sim):
    corpo = {"quantidade": 3, "semente": 42}
    assert cliente_sim.post("/simulador/gerar", json=corpo, headers=CHAVE).status_code == 200
    repetido = cliente_sim.post("/simulador/gerar", json=corpo, headers=CHAVE)
    assert repetido.status_code == 409
    assert "duplicado" in repetido.json()["detalhe"]


def test_paginacao_via_api_respeita_limite_e_cursor(cliente_sim):
    cliente_sim.post("/simulador/gerar", json={"quantidade": 5, "semente": 42}, headers=CHAVE)

    pagina1 = cliente_sim.get("/apontamentos?limite=2", headers=CHAVE).json()
    assert len(pagina1["itens"]) == 2
    assert pagina1["proximo_cursor"] is not None

    cursor = pagina1["proximo_cursor"].replace("|", "%7C")
    pagina2 = cliente_sim.get(f"/apontamentos?limite=2&cursor={cursor}", headers=CHAVE).json()
    assert len(pagina2["itens"]) == 2
    assert {i["id_origem"] for i in pagina1["itens"]}.isdisjoint(
        {i["id_origem"] for i in pagina2["itens"]}
    )

    invalido = cliente_sim.get("/apontamentos?cursor=lixo", headers=CHAVE)
    assert invalido.status_code == 400


def test_injetar_falha_via_api(cliente_sim):
    resposta = cliente_sim.post(
        "/simulador/injetar-falha",
        json={"tipo_falha": "TALHAO_INEXISTENTE", "quantidade": 2},
        headers=CHAVE,
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo == {"tipo_falha": "TALHAO_INEXISTENTE", "injetados": 2, "ids_origem": corpo["ids_origem"]}
    total = cliente_sim.get("/health").json()["total_apontamentos"]
    assert total == 2


def test_modo_indisponivel_responde_503_exceto_health(cliente_sim):
    cliente_sim.post("/simulador/gerar", json={"quantidade": 1, "semente": 1}, headers=CHAVE)
    ativar = cliente_sim.post("/simulador/modo-indisponivel", json={"duracao_segundos": 1}, headers=CHAVE)
    assert ativar.status_code == 200
    assert ativar.json()["modo_indisponivel_ate"] is not None

    indisponivel = cliente_sim.get("/apontamentos", headers=CHAVE)
    assert indisponivel.status_code == 503
    assert cliente_sim.get("/health").status_code == 200  # health fica de pé

    time.sleep(1.1)  # espera a janela passar
    assert cliente_sim.get("/apontamentos", headers=CHAVE).status_code == 200
