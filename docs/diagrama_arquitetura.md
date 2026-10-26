# Diagramas de Arquitetura — Integração Campo → ERP

> Diagramas Mermaid da demo fictícia. Fontes: código dos módulos (`simulador_campo/`, `integrador/`, `painel/`) e DDL de `db/`.

## 1. Arquitetura geral

```mermaid
flowchart LR
    subgraph ORIGEM["Módulo A — Simulador do Sistema de Campo (porta 8001)"]
        GER[gerador.py<br/>Faker pt_BR com semente]
        FAL[falhas.py<br/>injeção controlada]
        DB_S[(SQLite local<br/>apontamentos + duplicatas)]
        API_A[FastAPI<br/>X-API-Key: CAMPO_API_KEY]
        GER --> DB_S
        FAL --> DB_S
        DB_S --> API_A
    end

    subgraph INTEGRADOR["Módulo B — Serviço de Integração (porta 8002)"]
        AGD[agendador.py<br/>APScheduler: ciclo 5 min<br/>reprocessador 2 min]
        CIC[ciclo.py<br/>orquestração + lock]
        CON[consumidor.py<br/>httpx, retry 3x]
        VAL[validador.py<br/>contrato + cadastros]
        GRAV[gravador.py<br/>commit por registro]
        REJ[rejeitador.py<br/>fila p/ recuperáveis]
        REP[reprocessador.py<br/>revalidação + dead-letter]
        API_B[FastAPI admin<br/>X-API-Key: INT_API_KEY]
        AGD --> CIC --> CON
        CIC --> VAL
        VAL --> GRAV
        VAL --> REJ
        REJ --> REP
    end

    subgraph ERP["Oracle XE — container campo-erp-oracle (1521/XEPDB1)"]
        INT_T[("INTEGRACAO: INT_CURSOR, INT_LOTE,<br/>INT_REGISTRO, FILA_REPROCESSAMENTO,<br/>INT_TENTATIVA, TALHAO, EQUIPAMENTO,<br/>views V_*")]
        ERP_T[("ERP_SUPRIMENTOS: ITEM,<br/>APONTAMENTO_CAMPO")]
    end

    PAINEL["Módulo C — Painel Streamlit (8501)<br/>Visão Geral · Conciliação · Rejeições<br/>Fila · Lotes · Reprocessamento"]

    API_A -- "GET /apontamentos<br/>(paginado R9)" --> CON
    CIC -- "cursor, lote, registros" --> INT_T
    GRAV -- "INSERT APONTAMENTO_CAMPO" --> ERP_T
    VAL -- "SELECT cadastros" --> INT_T
    VAL -- "SELECT ITEM" --> ERP_T
    REP -- "revalida + grava" --> INT_T
    PAINEL -- "SELECT read-only (views V_*)" --> INT_T
    PAINEL -- "POST /reprocessar · POST /ciclo/executar" --> API_B
    API_B --> INT_T
```

Fluxo resumido: o **ciclo** (agendado a cada 5 min ou disparado via `POST /ciclo/executar`) lê o cursor, consome TODAS as páginas pendentes da origem, valida cada registro, grava os válidos no ERP e rejeita os inválidos (recuperáveis vão para a fila); só então fecha o lote e avança o cursor.

## 2. Sequência do ciclo de integração (com falhas)

```mermaid
sequenceDiagram
    autonumber
    participant JOB as Agendador (5 min)
    participant CIC as ciclo.executar_ciclo
    participant ORG as Simulador (8001)
    participant VAL as validador
    participant GRAV as gravador / rejeitador
    participant ORA as Oracle

    JOB->>CIC: dispara (lock anti-sobreposição)
    CIC->>ORA: ler_cursor() (semeia sentinela se ausente)
    CIC->>ORG: GET /apontamentos?cursor=...&limite=100
    alt 5xx / erro de rede
        ORG--xCIC: falha
        Note over CIC: retry 3x com backoff 1s/2s
        CIC->>ORA: criar lote FALHOU (INT-050/051)<br/>cursor NÃO avança
    else página ok
        ORG-->>CIC: {itens, proximo_cursor}
        Note over CIC: repete até len(itens) < limite<br/>cursor_final = último proximo_cursor
        CIC->>ORA: criar lote EM_ANDAMENTO
        loop para cada item
            CIC->>ORA: idempotência por id_origem
            alt já processado
                Note over CIC: conta duplicado (sem novo INSERT)
            else novo
                CIC->>VAL: validar(payload)
                alt válido
                    CIC->>GRAV: gravar() — commit por registro
                    GRAV->>ORA: INSERT INT_REGISTRO (RECEBIDO)
                    GRAV->>ORA: INSERT APONTAMENTO_CAMPO
                    GRAV->>ORA: UPDATE INT_REGISTRO → GRAVADO
                else inválido (INT-xxx)
                    CIC->>GRAV: rejeitar()
                    GRAV->>ORA: INSERT INT_REGISTRO (REJEITADO + CLOB)
                    opt erro recuperável
                        GRAV->>ORA: INSERT FILA_REPROCESSAMENTO (+5 min)
                    end
                end
            end
        end
        CIC->>ORA: fechar_lote (CONCLUIDO, totais recalculados)
        CIC->>ORA: avancar_cursor(cursor_final) — atomicamente
    end
```

Pontos-chave: **um registro inválido não derruba o lote** (regra 3); o **cursor só avança após o lote totalmente persistido** (regra 2) — crash no meio repega tudo e a idempotência converte os já gravados em duplicados; **erro de infraestrutura** (origem/banco) fecha o lote como `FALHOU` sem avançar o cursor.

## 3. Reprocessamento (fila + dead-letter)

```mermaid
sequenceDiagram
    autonumber
    participant JOB as Job reprocessador (2 min)
    participant REP as reprocessador
    participant VAL as validador (cadastros ATUAIS)
    participant ORA as Oracle

    JOB->>REP: executar_reprocessamento()
    loop itens vencidos
        REP->>ORA: SELECT ... FOR UPDATE SKIP LOCKED<br/>(claim atômico, PENDENTE → PROCESSANDO)
        REP->>VAL: revalida payload_original
        alt válido agora (ex.: cadastro corrigido)
            REP->>ORA: INSERT APONTAMENTO_CAMPO<br/>INT_REGISTRO → GRAVADO<br/>fila → CONCLUIDA<br/>INT_TENTATIVA SUCESSO
        else ainda inválido
            REP->>ORA: tentativas+1, próxima +5/+15/+60 min<br/>INT_TENTATIVA FALHA
            opt tentativas ≥ max (3)
                REP->>ORA: fila → DEAD_LETTER
            end
        end
    end
    Note over REP: POST /reprocessar usa o MESMO fluxo<br/>por item, com acionado_por=MANUAL,<br/>motivo obrigatório e reset de dead-letter
```

## 4. Máquinas de estado

### 4.1 `INT_LOTE.status`

```mermaid
stateDiagram-v2
    [*] --> EM_ANDAMENTO: criar_lote (início do ciclo)
    EM_ANDAMENTO --> CONCLUIDO: todos os registros processados<br/>(mes com rejeições — regra 3)
    EM_ANDAMENTO --> FALHOU: erro de infraestrutura<br/>(INT-050/051/052 no observacao)
    CONCLUIDO --> [*]
    FALHOU --> [*]
```

### 4.2 `INT_REGISTRO.status`

```mermaid
stateDiagram-v2
    [*] --> RECEBIDO: INSERT do gravador
    RECEBIDO --> GRAVADO: apontamento criado no ERP
    [*] --> REJEITADO: INSERT do rejeitador (erro INT-xxx)
    REJEITADO --> GRAVADO: reprocessamento venceu<br/>(cadastro corrigido)
    REJEITADO --> REJEITADO: tentativa falhou (codigo_erro atualizado)
    GRAVADO --> [*]
```

Nota: duplicados **não** geram nova linha em `INT_REGISTRO` — o reenvio do mesmo `id_origem` apenas incrementa `INT_LOTE.total_duplicados` (decisão de design; ver `decisoes_tecnicas.md`).

### 4.3 `FILA_REPROCESSAMENTO.situacao`

```mermaid
stateDiagram-v2
    [*] --> PENDENTE: rejeição recuperável (+5 min)<br/>ou reprocessamento manual
    PENDENTE --> PROCESSANDO: claim do job<br/>(FOR UPDATE SKIP LOCKED)
    PROCESSANDO --> CONCLUIDA: tentativa SUCESSO
    PROCESSANDO --> PENDENTE: tentativa FALHA<br/>(próxima em +5/+15/+60 min)
    PROCESSANDO --> DEAD_LETTER: tentativas ≥ max (3)
    DEAD_LETTER --> PENDENTE: reprocessamento manual<br/>(tentativas resetadas p/ 0)
    CONCLUIDA --> [*]
```
