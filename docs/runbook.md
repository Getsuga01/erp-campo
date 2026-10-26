# Runbook de Operação — Integração Campo → ERP

> Procedimentos para os 5 cenários de incidente exigidos pelo plano. Comandos prontos para PowerShell 5.1 (use `curl.exe` — no PowerShell, `curl` sozinho é alias de `Invoke-WebRequest`).
>
> Endereços e credenciais da demo: simulador `http://localhost:8001` (key `campo-dev-key-001`), integrador `http://localhost:8002` (key `integrador-dev-key-001`), painel `http://localhost:8501`, Oracle XE no container `campo-erp-oracle` (usuários/senhas fictícias em `db/01_schema.sql`).
>
> Prints das telas do painel serão anexados na Task 7 (E2E com o stack completo via docker compose).

---

## Cenário 1 — Origem fora do ar

**Sintoma**
- `GET /health` do integrador retorna `{"status": "degradado", "oracle": "ok", "origem": "erro"}`.
- Novos lotes fechando como `FALHOU` com `observacao` iniciando em `INT-050` (timeout/rede) ou `INT-051` (5xx).
- Log do integrador: `consumo da origem esgotou as tentativas`.

**Diagnóstico**
```powershell
curl.exe -s http://localhost:8002/health
curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/lotes?status=FALHOU&limite=5"
curl.exe -s http://localhost:8001/health   # origem responde? modo_indisponivel_ate ativo?
```
- Origem responde 503 com `modo_indisponivel_ate` preenchido → simulação ativa (aguardar expirar ou reiniciar o serviço, que limpa o estado em memória).
- Origem nem conecta → serviço caído (porta 8001 não escutando).

**Ação**
1. Re-subir a origem: `uvicorn --app-dir simulador_campo main:app --port 8001` (ou `docker compose up -d simulador` quando o compose completo existir — Task 7).
2. Confirmar `GET /health` da origem → `status: ok`.
3. NÃO é necessário mexer no cursor: o ciclo falhou **antes** de avançá-lo; o próximo ciclo repega tudo automaticamente. Para não esperar os 5 min do agendador: `curl.exe -s -X POST -H "X-API-Key: integrador-dev-key-001" http://localhost:8002/ciclo/executar`.

**Verificação**
- Novo lote `CONCLUIDO` (e rejeitado nenhum novo além dos já existentes).
- `curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/conciliacao"` → `total_divergencias: 0`.
- Painel **Visão Geral** sem card de divergência destacado.

---

## Cenário 2 — Cadastro ausente/inativo (rejeições recuperáveis)

**Sintoma**
- Rejeições `INT-002`/`INT-003`/`INT-004`/`INT-005` crescendo; itens `PENDENTE` na fila (tentativas 0/3, +5/+15/+60 min).
- Se ninguém corrige o cadastro: itens migram para `DEAD_LETTER` após 3 tentativas.

**Diagnóstico**
```powershell
curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/registros?codigo_erro=INT-002&limite=10"
curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/fila?situacao=PENDENTE&limite=10"
```
- Painel **Rejeições** (filtro por motivo) e **Fila**.
- Identificar o código de mestre ausente no `payload_original`:
```powershell
docker exec campo-erp-oracle bash -c "sqlplus -s INTEGRACAO/IntegracaoFicticia2026@localhost/XEPDB1 <<'EOF'
SELECT id_origem, codigo_erro, mensagem_erro FROM INT_REGISTRO WHERE codigo_erro LIKE 'INT-00%' AND status = 'REJEITADO' AND ROWNUM <= 10;
EXIT;
EOF"
```

**Ação**
1. Corrigir o cadastro no schema certo (`TALHAO`/`EQUIPAMENTO` em `INTEGRACAO`; `ITEM` em `ERP_SUPRIMENTOS`): INSERT do código ausente ou `UPDATE ... SET ativo = 1`.
2. Reprocessar os registros pendentes (o job automático revalida com cadastros ATUAIS em até 2 min; ou disparar na hora com motivo obrigatório):
```powershell
curl.exe -s -X POST -H "X-API-Key: integrador-dev-key-001" -H "Content-Type: application/json" `
  -d '{\"registro_ids\": [123], \"motivo\": \"talhao TAL-999 cadastrado\", \"acionado_por\": \"operador\"}' `
  http://localhost:8002/reprocessar
```
3. Itens `DEAD_LETTER` aceitam o mesmo comando (tentativas são resetadas automaticamente).

**Verificação**
- `GET /fila` → itens `CONCLUIDA`; `GET /registros?status=GRAVADO` mostra os reprocessados.
- `INT_TENTATIVA` registra `SUCESSO` (e `MANUAL` + motivo quando acionado manualmente).
- Painel **Reprocessamento** exibe o resultado; **Conciliação** absorve a migração pendentes → gravados sem divergência.

---

## Cenário 3 — Rajada de erro de contrato

**Sintoma**
- Pico súbito de rejeições **não recuperáveis** (`INT-001`, `INT-006`, `INT-007`, `INT-008`, `INT-009`, `INT-010`, `INT-011`) em um ou mais lotes `CONCLUIDO`.
- `top_5_erros` muda de formato no `GET /metricas` e no painel; taxa de sucesso cai.

**Diagnóstico**
```powershell
curl.exe -s -H "X-API-Key: integrador-dev-key-001" http://localhost:8002/metricas
```
- `INT-009` em massa → a origem passou a emitir outra `versao_contrato` (mudança de software de campo não coordenada).
- `INT-001`/`INT-011` em massa → deploy quebrado na origem (campos sumiram/tipos errados).
- Confirmar janela temporal: `SELECT * FROM V_TOP_ERROS;` + `recebido_em` dos registros.

**Ação**
1. **Não** reprocessar em massa — esses códigos são definitivos; reprocessar falha com o mesmo erro.
2. Conter a causa na origem (reverter deploy / restaurar versão de contrato / corrigir o gerador).
3. Registros afetados: revisar `payload_original` (CLOB em `INT_REGISTRO`) e, se o dado for recuperável do lado da origem, reenviar com novo ciclo após a correção — o mesmo `id_origem` reenviado conta como duplicado (protegido); a origem deve emitir **novo** `id_origem` se o desfecho anterior foi rejeição.
4. Registrar o incidente (lote, janela, volume, código dominante).

**Verificação**
- Lotes seguintes sem o `INT` da rajada (`GET /registros?codigo_erro=INT-009` vazio para janelas novas).
- `V_TOP_ERROS` estabiliza; taxa de sucesso volta ao patamar anterior no painel **Visão Geral**.

---

## Cenário 4 — Fila crescendo / dead-letter acumulando

**Sintoma**
- `V_FILA_STATUS`: `PENDENTE` com `qtd` subindo e `idade_mais_antigo_min` crescendo; `DEAD_LETTER` acumulando.
- Painel **Fila** mostra idade do item mais antigo destacada; `GET /metricas` → `fila_pendente_qtd`/`idade_fila_min`/`dead_letter_qtd` altos.

**Diagnóstico**
```powershell
curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/metricas"
curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/fila?situacao=PENDENTE&limite=50"
curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/fila?situacao=DEAD_LETTER&limite=50"
```
- Agrupar o motivo dominante (coluna `motivo` = mensagem do erro original).
- Cadastros ausentes em massa → cenário 2. Cadastros ok mas itens não saem → job do reprocessador parado? Verificar se o integrador está de pé e o log do job (roda a cada 2 min, `INT_REPROC_INTERVALO_MIN`).

**Ação**
1. Corrigir a causa raiz (cadastro, integração de mestres, origem).
2. Drenar em lote com motivo: coletar os `registro_id` pendentes/dead-letter e `POST /reprocessar` (um motivo por lote de acionamento; campo obrigatório).
3. Ajuste de urgência possível: subir `INT_MAX_TENTATIVAS`/intervalos via env se o time precisar de mais margem (valor default 3 tentativas).

**Verificação**
- `V_FILA_STATUS` drena; `dead_letter_qtd` para de crescer.
- `GET /conciliacao` → `pendentes_fila` converge para 0 (os itens viram gravados ou rejeitados definitivos) sem divergência.

---

## Cenário 5 — Divergência de conciliação

**Sintoma**
- `GET /conciliacao` retorna `total_divergencias > 0`; painel **Conciliação** exibe linhas em vermelho e **Visão Geral** destaca o card de divergência.
- `SELECT * FROM V_DIVERGENCIAS;` retorna linhas (esperado: sempre vazio).

**Diagnóstico**
```powershell
curl.exe -s -H "X-API-Key: integrador-dev-key-001" "http://localhost:8002/conciliacao?de=2026-10-24"
```
```powershell
docker exec campo-erp-oracle bash -c "sqlplus -s INTEGRACAO/IntegracaoFicticia2026@localhost/XEPDB1 <<'EOF'
SELECT * FROM V_DIVERGENCIAS ORDER BY dia, tipo;
EXIT;
EOF"
```
- A equação `recebidos = gravados + duplicados + rejeitados_definitivos + pendentes` é estrutural na view — divergência ≠ 0 indica manipulação FORA do pipeline ou bug.

**Ação**
1. Auditar o dia/tipo divergente: comparar `INT_REGISTRO` × `INT_LOTE` × `APONTAMENTO_CAMPO` (INSERTs manuais, UPDATEs de status fora do integrador, deletes).
2. Verificar lotes presos em `EM_ANDAMENTO` (serviço caiu no meio de um ciclo sem fechar o lote — o job não reprocessa lote aberto): fechar manualmente como `FALHOU` com observação, deixando o cursor repegar (regra 2).
3. Se a causa for bug do integrador, registrar o passo-a-passo no issue tracker com os ids envolvidos; os testes da Fase 5 (`python -m pytest`) reproduzem a equação em todos os fluxos — rodá-los ajuda a separar bug de manipulação manual.

**Verificação**
- `V_DIVERGENCIAS` vazia e `GET /conciliacao` → `total_divergencias: 0` para todas as janelas.
- Painel **Conciliação** sem linhas vermelhas; card de divergência zerado na **Visão Geral**.

---

## Referência rápida

| Consulta | Comando |
|---|---|
| Saúde do pipeline | `curl.exe -s http://localhost:8002/health` |
| Indicadores | `curl.exe -s -H "X-API-Key: integrador-dev-key-001" http://localhost:8002/metricas` |
| Fila por situação | `.../fila?situacao=PENDENTE` (`PROCESSANDO`/`CONCLUIDA`/`DEAD_LETTER`) |
| Rejeições por código | `.../registros?codigo_erro=INT-002&status=REJEITADO` |
| Lotes falhos | `.../lotes?status=FALHOU` |
| Conciliação por período | `.../conciliacao?de=AAAA-MM-DD&ate=AAAA-MM-DD` |
| Forçar ciclo agora | `POST .../ciclo/executar` (409 se já em andamento) |
| Reprocessar com motivo | `POST .../reprocessar` `{registro_ids, motivo, acionado_por}` |
| SQL direto | `docker exec campo-erp-oracle bash -c "sqlplus -s INTEGRACAO/IntegracaoFicticia2026@localhost/XEPDB1 <<'EOF' ... EXIT; EOF"` |
