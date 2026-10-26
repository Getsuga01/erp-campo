# Contrato de Dados — Apontamentos do Sistema de Campo (v1.0)

> Fonte de verdade: `simulador_campo/models.py` (origem) e `integrador/models.py` + `integrador/validador.py` (validação). Este documento descreve a versão **1.0** do contrato, a única suportada pelo integrador (`versao_contrato` diferente → `INT-009`).

## 1. Visão geral

O sistema de campo (simulado pelo **Módulo A**, porta 8001) emite apontamentos operacionais de três tipos — `PESAGEM`, `MAQUINA` e `INSUMO`. O integrador (**Módulo B**, porta 8002) consome esses apontamentos via `GET /apontamentos`, valida o contrato abaixo, grava no Oracle (schema `ERP_SUPRIMENTOS.APONTAMENTO_CAMPO`) e registra a rastreabilidade em `INTEGRACAO.INT_REGISTRO`.

Todo payload é um objeto JSON com os campos da seção 2. Campos irrelevantes ao tipo seguem como `null` (nunca omitidos) na origem; no integrador, `null` e ausente são equivalentes.

## 2. Campos do payload

| Campo | Tipo/formato | Obrigatório | Regras |
|---|---|---|---|
| `id_origem` | string UUID4 | sempre | Identificador único do apontamento na origem. Base da idempotência (UK em `INT_REGISTRO.id_origem`). Reenvio não duplica efeito no ERP — apenas contabiliza duplicado no lote. |
| `tipo` | enum `PESAGEM` \| `MAQUINA` \| `INSUMO` | sempre | Valor desconhecido → `INT-011` (payload não parseável). |
| `data_hora` | string ISO-8601 **UTC** com sufixo `Z`, ex. `2026-10-24T14:30:00Z` | sempre | Campo de negócio. Não pode estar no futuro além da tolerância de **5 minutos** (`INT_ORACLE… INT_TOLERANCIA_FUTURO_MIN`, ver 2.6) → `INT-007`. Sem timezone é interpretado como UTC. |
| `talhao_codigo` | string `TAL-001`…`TAL-020` | sempre | Deve existir no cadastro (`INT-002`) e estar ativo (`INT-003`). Ativos na carga fictícia: TAL-001…TAL-018; TAL-019/TAL-020 inativos. |
| `equipamento_codigo` | string `EQP-001`…`EQP-015` \| null | **PESAGEM e MAQUINA**; `null` em INSUMO | Deve existir e estar ativo (`INT-004`). Ativos: EQP-001…EQP-014; EQP-015 inativo. |
| `item_codigo` | string `ITEM-001`…`ITEM-010` \| null | **INSUMO**; `null` nos demais | Deve existir no cadastro do ERP fictício (`INT-005`). |
| `peso_bruto` | number(12,3), kg \| null | **PESAGEM** | Acima de `INT_PESO_LIMITE_ALERTA` (default **60.000 kg**) gera log WARNING, mas **grava**. |
| `peso_tara` | number(12,3), kg \| null | **PESAGEM** | — |
| `peso_liquido` | number(12,3), kg \| null | **PESAGEM** | Deve satisfazer `peso_liquido = peso_bruto − peso_tara` (tolerância de arredondamento **0,001 kg**) e ser `> 0`; senão `INT-006`. |
| `horas_maquina` | number(6,2), horas \| null | **MAQUINA** | Deve estar em `(0, 24]`; senão `INT-008`. |
| `quantidade` | number(12,3) \| null | **INSUMO** | Deve ser `> 0`; senão `INT-010`. |
| `operador` | string (≤120) | sempre | Nome fictício do operador de campo. |
| `observacao` | string (≤500) \| null | opcional | — |
| `versao_contrato` | string literal `"1.0"` | sempre | Única versão suportada; qualquer outro valor → `INT-009`. |

**Campos extras desconhecidos**: ignorados com log WARNING (nunca causam rejeição).

**Campos obrigatórios ausentes** (incluindo o obrigatório *do tipo*, ex. `equipamento_codigo` ausente em PESAGEM): `INT-001`.

### Exemplos por tipo

```json
{
  "id_origem": "3f2a1b2c-0000-4000-8000-000000000001",
  "tipo": "PESAGEM",
  "data_hora": "2026-10-24T14:30:00Z",
  "talhao_codigo": "TAL-001",
  "equipamento_codigo": "EQP-003",
  "item_codigo": null,
  "peso_bruto": 25400.500,
  "peso_tara": 4200.000,
  "peso_liquido": 21200.500,
  "horas_maquina": null,
  "quantidade": null,
  "operador": "Maria Souza",
  "observacao": "pesagem de carregamento",
  "versao_contrato": "1.0"
}
```

```json
{
  "id_origem": "3f2a1b2c-0000-4000-8000-000000000002",
  "tipo": "MAQUINA",
  "data_hora": "2026-10-24T15:05:00Z",
  "talhao_codigo": "TAL-002",
  "equipamento_codigo": "EQP-001",
  "item_codigo": null, "peso_bruto": null, "peso_tara": null, "peso_liquido": null,
  "horas_maquina": 8.50,
  "quantidade": null,
  "operador": "João Pereira",
  "observacao": null,
  "versao_contrato": "1.0"
}
```

```json
{
  "id_origem": "3f2a1b2c-0000-4000-8000-000000000003",
  "tipo": "INSUMO",
  "data_hora": "2026-10-24T16:40:00Z",
  "talhao_codigo": "TAL-003",
  "equipamento_codigo": null,
  "item_codigo": "ITEM-007",
  "peso_bruto": null, "peso_tara": null, "peso_liquido": null,
  "horas_maquina": null,
  "quantidade": 350.750,
  "operador": "Ana Lima",
  "observacao": null,
  "versao_contrato": "1.0"
}
```

## 3. API da origem (Módulo A — simulador, porta 8001)

Autenticação: header **`X-API-Key`** em TODAS as rotas, exceto `GET /health`. Valor da demo: `campo-dev-key-001` (env `CAMPO_API_KEY`). Erro de auth: `401 {"detalhe": "X-API-Key ausente ou invalida"}`.

### 3.1 `GET /apontamentos` — listagem paginada

Parâmetros: `limite` (1–500, default 100) e `cursor` (opaque, formato `created_at|id`).

Resposta:

```json
{
  "itens": [ <payload completo da seção 2>, ... ],
  "proximo_cursor": "2026-10-24T14:30:00.000001Z|42"
}
```

**Contrato de paginação (ruling R9)**:
- A ordem é a **ordem de ingestão** (`created_at`, `id`) — não a `data_hora` de negócio. Assim, um registro novo com `data_hora` antiga nunca é perdido.
- `proximo_cursor` é **SEMPRE a posição da última linha servida** quando ≥ 1 item foi servido (inclusive na última página parcial).
- `proximo_cursor` é `null` **SOMENTE em página vazia**.
- Regra de consumo do integrador: paginar até receber `len(itens) < limite`; o cursor final do ciclo é o ÚLTIMO `proximo_cursor` recebido.
- Cursor inválido → `400 {"detalhe": "cursor invalido"}`.

### 3.2 `GET /apontamentos/{id_origem}`

`200` com o payload, ou `404 {"detalhe": "apontamento nao encontrado"}`.

### 3.3 `POST /simulador/gerar`

Gera N apontamentos **válidos** com semente (reprodutíveis) e persiste no SQLite local.

```json
{"quantidade": 100, "semente": 42, "tipos": null}
```

`quantidade` 1–1000; `tipos` opcional (subset de PESAGEM/MAQUINA/INSUMO; default todos, distribuição ~40/30/30). Resposta: `{"gerados": N, "ids_origem": [...]}`. Regenerar a mesma semente sem limpar a base → `409` (UK de `id_origem`).

### 3.4 `POST /simulador/injetar-falha`

Gera registros que VIOLAM uma regra específica (o simulador serve tudo; quem rejeita é o integrador):

```json
{"tipo_falha": "PESO_NEGATIVO", "quantidade": 3}
```

| `tipo_falha` | Violação produzida | Código esperado no integrador |
|---|---|---|
| `TALHAO_INEXISTENTE` | `talhao_codigo = "TAL-999"` | `INT-002` (recuperável → fila) |
| `PESO_NEGATIVO` | `peso_tara > peso_bruto` (líquido < 0) | `INT-006` |
| `DUPLICATA` | reinsere `id_origem` já existente (tabela própria de duplicatas) | duplicado (contagem no lote) |
| `DATA_FUTURA` | `data_hora` = agora + 2 h | `INT-007` |
| `CAMPO_AUSENTE` | remove `talhao_codigo` do payload | `INT-001` |
| `ITEM_INEXISTENTE` | `item_codigo = "ITEM-999"` | `INT-005` (recuperável → fila) |
| `HORAS_INVALIDAS` | `horas_maquina = 25.0` | `INT-008` |

### 3.5 `POST /simulador/modo-indisponivel`

Simula a origem fora do ar por N segundos (middleware responde `503` em tudo, exceto `/health`): `{"duracao_segundos": 60}` (1–3600).

### 3.6 `GET /health` (sem auth)

`{"status": "ok", "sqlite": "ok", "gerador": "ok", "total_apontamentos": N, "modo_indisponivel_ate": null}`.

## 4. Efeitos no ERP (Módulo B)

Payload válido → 1 linha em `ERP_SUPRIMENTOS.APONTAMENTO_CAMPO` (FKs resolvidas por código: `talhao_id`, `equipamento_id`, `item_id`; `data_hora` normalizada para UTC) + `INT_REGISTRO.status = GRAVADO`. Payload inválido → `INT_REGISTRO.status = REJEITADO` com `codigo_erro`/`mensagem_erro` e o payload original íntegro em CLOB; se o erro for recuperável, entra na `FILA_REPROCESSAMENTO`.

## 5. Versionamento

Mudanças no contrato exigem nova `versao_contrato` (ex. `"2.0"`). O integrador rejeita versões não suportadas com `INT-009` (não recuperável) — a evolução do contrato é coordenada entre os módulos antes de qualquer mudança simultânea.
