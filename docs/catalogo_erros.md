# Catálogo de Erros — INT-001 a INT-099

> Fonte de verdade: `integrador/erros.py` (enum `CATALOGO`). Convenção de intervalos (decisão do controller): **INT-012 a INT-049** reservados para novas regras de negócio; **INT-051 a INT-098** reservados para erros técnicos/infraestrutura.

## 1. Semântica das classes de erro

- **`ErroRejeicao`** — rejeição de um registro individual (validação de contrato/negócio). O lote **continha** processando os demais (regra 3: registro inválido não derruba lote).
- **`ErroCiclo`** — falha de infraestrutura que **aborta o ciclo inteiro**. Nenhum registro é rejeitado individualmente; o lote fecha como `FALHOU` com o código na `observacao` e o cursor NÃO avança — o próximo ciclo repega tudo (idempotência cuida dos já processados).

A coluna **recuperável** indica se o registro rejeitado pode vencer no reprocessamento (geralmente após correção de cadastro). Recuperáveis são **enfileirados** automaticamente (`FILA_REPROCESSAMENTO`, backoff 5/15/60 min, máximo 3 tentativas → `DEAD_LETTER`). Não recuperáveis ficam como rejeição definitiva (podem ser reprocessados manualmente, que cria fila nova).

## 2. Tabela de códigos

| Código | Mensagem | Recuperável | Exemplo de payload/condição que causa | Efeito |
|---|---|---|---|---|
| `INT-001` | campo obrigatório ausente | ❌ | `{"tipo": "PESAGEM", ...}` sem `talhao_codigo`; PESAGEM sem `equipamento_codigo`; INSUMO sem `item_codigo` | Rejeição definitiva |
| `INT-002` | talhão inexistente no cadastro | ✅ | `"talhao_codigo": "TAL-999"` (não cadastrado) | Rejeição + fila |
| `INT-003` | talhão inativo no cadastro | ✅ | `"talhao_codigo": "TAL-019"` (ativo = 0 na carga) | Rejeição + fila |
| `INT-004` | equipamento inexistente ou inativo no cadastro | ✅ | `"equipamento_codigo": "EQP-999"` ou `"EQP-015"` (inativo) | Rejeição + fila |
| `INT-005` | item inexistente no cadastro | ✅ | `"item_codigo": "ITEM-999"` | Rejeição + fila |
| `INT-006` | peso líquido inválido (≠ bruto − tara ou ≤ 0) | ❌ | `peso_bruto=10000, peso_tara=3000, peso_liquido=6500` (diferença > 0,001 kg); ou `peso_tara > peso_bruto` | Rejeição definitiva |
| `INT-007` | data_hora no futuro além da tolerância | ❌ | `"data_hora": <agora + 10 min>` (tolerância de 5 min, `INT_TOLERANCIA_FUTURO_MIN`) | Rejeição definitiva |
| `INT-008` | horas_maquina fora do intervalo (0, 24] | ❌ | `"horas_maquina": 25.0` ou `0` | Rejeição definitiva |
| `INT-009` | versao_contrato não suportada | ❌ | `"versao_contrato": "2.0"` (suportada: `"1.0"`) | Rejeição definitiva |
| `INT-010` | quantidade ≤ 0 em INSUMO | ❌ | `"quantidade": 0` | Rejeição definitiva |
| `INT-011` | tipo desconhecido / payload não parseável | ❌ | `"tipo": "TRANSFERENCIA"`; payload que não é objeto JSON; tipos errados nos campos | Rejeição definitiva (o `tipo` persistido usa fallback `PESAGEM` para respeitar o CHECK — o payload original fica íntegro no CLOB) |
| `INT-050` | origem indisponível / timeout | ✅ (ciclo) | origem não responde, timeout HTTP (`INT_TIMEOUT_HTTP_SEG`, default 10 s) | **ErroCiclo** após 3 tentativas → lote `FALHOU`, cursor não avança |
| `INT-051` | erro 5xx da origem | ✅ (ciclo) | `POST /simulador/modo-indisponivel` ativo → `503` nas chamadas | **ErroCiclo** após 3 tentativas → lote `FALHOU` |
| `INT-052` | banco Oracle indisponível | ✅ (ciclo) | Oracle fora do ar / erro de SQL no meio do lote | **ErroCiclo** → lote `FALHOU` (com os totais do que foi gravado até então), cursor não avança |
| `INT-099` | erro interno inesperado | ❌ | exceção não prevista no processamento de um registro; 4xx inesperado da origem (ex. 404); resposta fora do contrato de paginação | Registro: rejeição definitiva. Ciclo: aborto |

## 3. Onde cada código aparece

- **`INT_REGISTRO.codigo_erro`** — rejeições (INT-001…011, 099). Consultável por `GET /registros?codigo_erro=INT-002` e agregado na view `V_TOP_ERROS` (top 5 no `GET /metricas` e no painel).
- **`INT_LOTE.observacao`** — erros de ciclo no formato `"INT-051: erro 5xx da origem: HTTP 503"` (lotes `FALHOU`).
- **`INT_TENTATIVA.codigo_erro`** — falha de cada tentativa de reprocessamento (histórico).
- **Logs JSON** do integrador (`logger.py`) carregam `codigo_erro` como campo estruturado em WARNING/ERROR.

## 4. Reprocessamento por código

| Situação | Comportamento |
|---|---|
| Recuperável (002/003/004/005) rejeitado no ciclo | Enfileira automaticamente: tentativas 0/3, próximas tentativas +5, +15, +60 min (job a cada 2 min pega vencidos) |
| Sucesso em tentativa | Registro vira `GRAVADO`, apontamento criado, fila `CONCLUIDA`, `INT_TENTATIVA` com `SUCESSO` |
| Esgota as 3 tentativas | Fila `DEAD_LETTER`; registro permanece `REJEITADO` (vira "rejeitado definitivo" na conciliação) |
| Manual (`POST /reprocessar`) | Aceita qualquer `REJEITADO` (cria fila nova se não recuperável), reseta tentativas se vinha de `DEAD_LETTER`, registra `acionado_por=MANUAL` + motivo obrigatório em `INT_TENTATIVA.observacao` |
