# Decisões Técnicas — Projeto 2 (Integração Campo → ERP)

> Justificativas de design com trade-offs. Fontes: código, ledger SDD (`progress.md`, rulings R1–R9) e plano. Cada item indica o custo se a decisão estiver errada.

## 1. Idempotência por `id_origem` — sem nova linha para duplicados

**Decisão**: `INT_REGISTRO.id_origem` tem UK. O reenvio do mesmo `id_origem` (qualquer que seja o status anterior) **não** gera nova linha em `INT_REGISTRO` nem em `APONTAMENTO_CAMPO` — apenas incrementa `INT_LOTE.total_duplicados` do lote corrente, preservando o desfecho da primeira ocorrência.

**Por quê**: mantém `INT_REGISTRO` 1:1 com apontamentos únicos (a conciliação por registro fica trivial) e evita efeitos duplicados no ERP quando o cursor repega registros já processados (crash, rede, reprocesso).

**Trade-off**: o total de duplicados vive no cabeçalho do lote (não em `INT_REGISTRO`), então a equação de conciliação `recebidos = gravados + duplicados + rejeitados_def + pendentes` combina a tabela de registros com os contadores dos lotes — a view `V_CONCILIACAO_DIA_TIPO` reflete exatamente isso (status `DUPLICADO` existe no CHECK mas a implementação não o usa).

**Custo se errar**: duplicação de dados no ERP ou quebra da conciliação.

## 2. Cursor só avança após o lote totalmente persistido

**Decisão**: `avancar_cursor` é um UPDATE atômico executado SOMENTE depois do `fechar_lote`. Em falha (origem, banco, crash), o cursor antigo faz o próximo ciclo **repegar** tudo; os já gravados voltam como duplicados (item 1).

**Por quê**: semântica at-most-once×idempotente simples de raciocinar; nenhum registro é perdido entre o crash e o avanço do cursor.

**Trade-off**: re-consumo deliberado após falhas (tráfego extra e contagem de duplicados) — aceitável na escala da demo.

**Custo se errar**: perda silenciosa de registros (o pior modo de falha de uma integração).

## 3. Commit por registro, não por lote

**Decisão**: `gravador.gravar` faz INSERT `INT_REGISTRO` (RECEBIDO) → INSERT `APONTAMENTO_CAMPO` → UPDATE para GRAVADO **na mesma transação, por registro**.

**Por quê**: combinado com o item 2, um crash no meio do lote preserva os registros já gravados e repega só os restantes. Commit por lote reverteria trabalho válido; commit por registro isola o dano.

**Trade-off**: mais round-trips ao banco (irrelevante no volume da demo; em escala real, batches small-N amortizariam).

## 4. Erros de ciclo × rejeições de registro

**Decisão**: validações de contrato/negócio (`ErroRejeicao`) rejeitam o registro individual sem derrubar o lote (regra 3). Falhas de infraestrutura (`ErroCiclo`, INT-050/051/052) abortam o ciclo, fecham o lote como `FALHOU` e **não** avançam o cursor. Erros inesperados no processamento de um registro viram `INT-099` (não recuperável) — o lote segue.

**Por quê**: um lote com 10.000 registros e 3 inválidos deve fechar `CONCLUIDO` com 3 rejeições; uma origem fora do ar não deve gerar 10.000 rejeições falsas (o próximo ciclo repega tudo).

**Custo se errar**: rejeições em massa em incidentes de infraestrutura, ou lotes eternamente travados.

## 5. Fila de reprocessamento: backoff fixo 5/15/60 + dead-letter

**Decisão**: rejeições **recuperáveis** (cadastro: INT-002/003/004/005) entram em `FILA_REPROCESSAMENTO` com próximas tentativas em +5, +15 e +60 min; ao esgotar 3 tentativas (`INT_MAX_TENTATIVAS`), o item vai para `DEAD_LETTER`. O job roda a cada 2 min e pega vencidos.

**Por quê**: cadastro ausente costuma ser corrigido por um humano em minutos/horas; backoff crescente evita martelar o banco; dead-letter dá um fim previsível para revisão manual. A revalidação usa cadastros **ATUAIS** (cada tentativa consulta o banco — nenhum cache).

**Trade-off**: intervalos fixos (não exponenciais com jitter) — suficiente para a demo; em escala multi-worker real, ver item 7.

**Custo se errar**: fila infinita ou reprocessamento tempestuoso.

## 6. Reprocessamento manual com trilha de auditoria

**Decisão**: `POST /reprocessar` exige `motivo`; cada tentativa (automática ou manual) grava linha imutável em `INT_TENTATIVA` com `resultado`, `codigo_erro`, `acionado_por` (SISTEMA/MANUAL — CHECK no DDL) e `observacao`. Manual vindo de `DEAD_LETTER` reseta as tentativas; registro `REJEITADO` sem fila (erro não recuperável) ganha fila nova.

**Por quê**: quem reprocessou e por quê precisa ser auditável — é a mesma exigência de um ERP real.

**Custo se errar**: reprocessamentos anônimos e irrepetíveis em incidente.

## 7. Concorrência: lock de ciclo + `FOR UPDATE SKIP LOCKED` (single-worker)

**Decisão**: um `threading.Lock` no `executar_ciclo` evita sobreposição job×manual (retorna `JA_EM_ANDAMENTO` → HTTP 409). O reprocessador faz *claim* com `SELECT ... ROWNUM = 1 FOR UPDATE SKIP LOCKED`.

**Limitação conhecida (nota da Task 3)**: o `ROWNUM = 1` ANTES do `FOR UPDATE` faz sentido em single-worker — em multi-worker real, o SKIP LOCKED perde eficácia com a ordenação pré-lock. Para N workers, seria `FETCH FIRST` com ordenação estável + SKIP LOCKED por item em transação curta. Registrado como limitação, não corrigido (demo é single-worker).

**Custo se errar**: double-processing em ambiente multi-worker (a idempotência por `id_origem` ainda protege o ERP).

## 8. Paginação da origem por ordem de ingestão + emenda R9

**Decisão**: o cursor da API do simulador é `(created_at, id)` — ordem de **ingestão**, não a `data_hora` de negócio. `proximo_cursor` é SEMPRE a última linha servida (≥1 item); `null` somente em página vazia; o consumidor para quando `len(itens) < limite` e avança o cursor do banco para o último `proximo_cursor` recebido (ruling R9, supersed a semântica anterior de "null no fim").

**Por quê**: registros novos com `data_hora` antiga (relógio do apontador) nunca são perdidos; e a semântica antiga impedia o integrador de derivar a posição exata após uma página parcial final (alternativa de relógio/t0 acoplaria os relógios das duas partes).

**Custo se errar**: perda de registros tardios ou re-consumo infinito.

## 9. Duplicatas do simulador em tabela própria

**Decisão** (documentada em `simulador_campo/database.py`): a tabela `apontamentos` mantém a UK de `id_origem`; a falha `DUPLICATA` grava na tabela auxiliar `apontamentos_duplicados` (mesma estrutura, sem UK). O cursor global `(created_at, id)` usa um contador único entre as duas tabelas para continuar estável no UNION.

**Por quê**: preserva a linha original íntegra e expõe a duplicidade na listagem — quem detecta é o integrador, exercitando a idempotência de verdade.

**Custo se errar**: `sqlite3.IntegrityError` na injeção de duplicatas ou perda do contrato de paginação.

## 10. `python-oracledb` em modo THIN (ruling R3)

**Decisão**: conexão em modo thin (puro Python, sem Oracle Instant Client), pool criado sob demanda (o serviço sobe mesmo com o banco fora — `iniciar_pool` registra falha no log).

**Por quê**: imagem Docker menor, build sem binário nativo, prática oficial atual. Pool sob demanda degrada graciosamente no boot.

**Trade-off**: thin tem limitações de features avançadas (irrelevantes aqui).

**Custo se errar**: Dockerfile quebrado ou boot que falha quando o banco atrasa.

## 11. Banco em UTC, exibição em America/São_Paulo (ruling R7)

**Decisão**: `APONTAMENTO_CAMPO.data_hora` e todos os `TIMESTAMP` de controle são UTC (o container roda em UTC; o integrador normaliza `data_hora` para UTC antes de gravar). O painel converte para `America/Sao_Paulo` **nos pontos de exibição** (nunca no SQL).

**Custo se errar**: divergências de conciliação por dia com fronteiras de fuso.

## 12. Reprodutibilidade por semente (com exceção documentada)

**Decisão**: `gerador.gerar_lote(quantidade, semente)` com `Faker.seed` + `seed_instance` + `random.Random(semente)` gera os MESMOS `id_origem`/valores. Exceção documentada: `data_hora` deriva de um offset aleatório (sempre o mesmo) aplicado a um "agora" capturado na geração — entre execuções o que se repete é o offset, não o instante absoluto.

**Por quê**: testes determinísticos (85 testes dependem disso) e demo reproduzível.

**Custo se errar**: testes flaky.

## 13. Testes sem Oracle local (ruling R5) + trava anti-Oracle-real

**Decisão**: `tests/conftest.py` carrega os módulos de cada pacote num contexto isolado de `sys.path`/`sys.modules` (integrador e simulador colidem em nomes top-level como `config`/`models`) e troca `sessao`/`transacao` do `oracle_client` por um **BancoFake** em memória que reproduz a semântica das SQL usadas, com transações por snapshot/rollback (fidelidade ao commit por registro). A regra 12 usa o consumidor REAL com `httpx.MockTransport`. Uma fixture **autouse** bloqueia o pool Oracle real: qualquer vazamento de teste para o banco de desenvolvimento falha alto.

**Motivo da trava (incidente Task 5)**: uma versão inicial do loader re-executava dependências em instâncias sem patch; com o Oracle XE real no ar, execuções iniciais gravaram dados de teste no banco de desenvolvimento. O banco foi limpo cirurgicamente, o loader foi corrigido (pacote inteiro carregado em um único contexto) e a trava foi adicionada para que vazamento futuro seja impossível de passar despercebido.

**Custo se errar**: testes que dependem de Oracle quebram em CI/outras máquinas; ou pior — poluem ambientes compartilhados.

## 14. Senhas e chaves fictícias via ambiente

**Decisão**: nenhum segredo real no repo. Senhas fictícias ficam em `db/01_schema.sql`/defaults de código (ex.: `IntegracaoFicticia2026`) e são sobrescritíveis por env (`INT_ORACLE_SENHA`, `CAMPO_API_KEY`, `INT_API_KEY`, `ORACLE_PASSWORD` no compose). O logger NUNCA emite senha/API key.

**Nota deferida (Task 3)**: defaults de senha no código são aceitáveis para a demo local, mas a Task 7 deve garantir o `.env.example` completo (ruling R8).

## 15. Arquitetura de pastas dos módulos — imports top-level absolutos

**Decisão**: cada módulo (simulador/integrador/painel) usa imports absolutos top-level (`from models import ...`) e roda a partir da própria pasta (`uvicorn --app-dir <pasta>`). O painel usa o pacote próprio `paginas/` (não a convenção nativa `pages/` do Streamlit, que conflita).

**Trade-off**: exige o loader do conftest nos testes (item 13) e `--app-dir`/`WORKDIR` corretos nos Dockerfiles.

**Custo se errar**: ImportError entre módulos com nomes repetidos (`config`, `models`).
