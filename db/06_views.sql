--------------------------------------------------------------------------------
-- Projeto 2 (demo fictícia) — Integração Sistema de Campo → ERP
--
-- Arquivo ....: 06_views.sql
-- Tarefa .....: 1.7 — Views de conciliação e indicadores (base do painel)
-- Objetivo ...:
--   V_CONCILIACAO_DIA_TIPO : agregação por dia (UTC) × tipo garantindo a
--     equação  recebidos = gravados + duplicados + rejeitados + pendentes_fila
--     (divergencia = recebidos - gravados - duplicados - rejeitados -
--      pendentes_fila; esperado sempre 0).
--     Partição sem interseção de cada registro de INT_REGISTRO:
--       GRAVADO                              -> gravados
--       DUPLICADO                            -> duplicados
--       RECEBIDO / PENDENTE_FILA             -> pendentes_fila (sem desfecho)
--       REJEITADO com fila PENDENTE ou
--         PROCESSANDO                        -> pendentes_fila (recuperável)
--       REJEITADO sem fila recuperável
--         (DEAD_LETTER, CONCLUIDA sem êxito,
--          ou sem fila)                      -> rejeitados (definitivo)
--   V_INDICADORES_LOTE : totais, taxa de sucesso, duração e conferência de
--                        registros vinculados por lote.
--   V_FILA_STATUS      : quantidade e idade (minutos) do item mais antigo
--                        por situação da fila.
--   V_TOP_ERROS        : quantidade de registros por código de erro (ordenável
--                        por qtd / ultima_ocorrencia).
--   V_DIVERGENCIAS     : dias/tipos em que a equação NÃO fecha (visão de
--                        auditoria; espera-se sempre vazia).
--------------------------------------------------------------------------------
WHENEVER SQLERROR EXIT SQL.SQLCODE;

CREATE OR REPLACE VIEW INTEGRACAO.V_CONCILIACAO_DIA_TIPO AS
SELECT TRUNC(r.recebido_em) AS dia,
       r.tipo,
       COUNT(*) AS recebidos,
       SUM(CASE WHEN r.status = 'GRAVADO' THEN 1 ELSE 0 END) AS gravados,
       SUM(CASE WHEN r.status = 'DUPLICADO' THEN 1 ELSE 0 END) AS duplicados,
       SUM(CASE WHEN r.status = 'REJEITADO' AND NVL(rec.recuperavel, 0) = 0
                THEN 1 ELSE 0 END) AS rejeitados,
       SUM(CASE WHEN r.status IN ('RECEBIDO', 'PENDENTE_FILA')
                 OR (r.status = 'REJEITADO' AND NVL(rec.recuperavel, 0) = 1)
                THEN 1 ELSE 0 END) AS pendentes_fila,
       COUNT(*)
         - SUM(CASE WHEN r.status = 'GRAVADO' THEN 1 ELSE 0 END)
         - SUM(CASE WHEN r.status = 'DUPLICADO' THEN 1 ELSE 0 END)
         - SUM(CASE WHEN r.status = 'REJEITADO' AND NVL(rec.recuperavel, 0) = 0
                    THEN 1 ELSE 0 END)
         - SUM(CASE WHEN r.status IN ('RECEBIDO', 'PENDENTE_FILA')
                     OR (r.status = 'REJEITADO' AND NVL(rec.recuperavel, 0) = 1)
                    THEN 1 ELSE 0 END) AS divergencia
  FROM INTEGRACAO.INT_REGISTRO r
  LEFT JOIN (SELECT registro_id,
                    MAX(CASE WHEN situacao IN ('PENDENTE', 'PROCESSANDO')
                             THEN 1 ELSE 0 END) AS recuperavel
               FROM INTEGRACAO.FILA_REPROCESSAMENTO
              GROUP BY registro_id) rec
         ON rec.registro_id = r.id
 GROUP BY TRUNC(r.recebido_em), r.tipo;

CREATE OR REPLACE VIEW INTEGRACAO.V_INDICADORES_LOTE AS
SELECT l.id AS lote_id,
       l.status,
       l.total_recebidos,
       l.total_gravados,
       l.total_rejeitados,
       l.total_duplicados,
       CASE WHEN l.total_recebidos > 0
            THEN ROUND(l.total_gravados * 100 / l.total_recebidos, 2)
       END AS taxa_sucesso_pct,
       ROUND((CAST(l.fechado_em AS DATE) - CAST(l.iniciado_em AS DATE)) * 1440, 2)
         AS duracao_minutos,
       l.iniciado_em,
       l.fechado_em,
       COUNT(r.id) AS qtd_registros_vinculados
  FROM INTEGRACAO.INT_LOTE l
  LEFT JOIN INTEGRACAO.INT_REGISTRO r
         ON r.lote_id = l.id
 GROUP BY l.id,
          l.status,
          l.total_recebidos,
          l.total_gravados,
          l.total_rejeitados,
          l.total_duplicados,
          l.iniciado_em,
          l.fechado_em;

CREATE OR REPLACE VIEW INTEGRACAO.V_FILA_STATUS AS
SELECT situacao,
       qtd,
       EXTRACT(DAY FROM idade) * 1440
     + EXTRACT(HOUR FROM idade) * 60
     + EXTRACT(MINUTE FROM idade) AS idade_mais_antigo_min
  FROM (SELECT f.situacao AS situacao,
               COUNT(*) AS qtd,
               CAST(SYSTIMESTAMP AS TIMESTAMP) - MIN(f.criado_em) AS idade
          FROM INTEGRACAO.FILA_REPROCESSAMENTO f
         GROUP BY f.situacao);

CREATE OR REPLACE VIEW INTEGRACAO.V_TOP_ERROS AS
SELECT r.codigo_erro,
       COUNT(*) AS qtd,
       MAX(r.recebido_em) AS ultima_ocorrencia
  FROM INTEGRACAO.INT_REGISTRO r
 WHERE r.codigo_erro IS NOT NULL
 GROUP BY r.codigo_erro;

CREATE OR REPLACE VIEW INTEGRACAO.V_DIVERGENCIAS AS
SELECT dia,
       tipo,
       recebidos,
       gravados,
       duplicados,
       rejeitados,
       pendentes_fila,
       divergencia
  FROM INTEGRACAO.V_CONCILIACAO_DIA_TIPO
 WHERE divergencia <> 0;

EXIT;
