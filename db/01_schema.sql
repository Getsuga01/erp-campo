--------------------------------------------------------------------------------
-- Projeto 2 (demo fictícia) — Integração Sistema de Campo → ERP
--
-- Arquivo ....: 01_schema.sql
-- Tarefa .....: 1.2 — Criar schemas de banco
-- Objetivo ...: Criar os usuários/schemas usados pelo pipeline:
--                 * ERP_SUPRIMENTOS : dados de negócio do ERP fictício
--                   ("Projeto 1" autocontido desta demo) — dono de ITEM e
--                   APONTAMENTO_CAMPO.
--                 * INTEGRACAO      : tabelas operacionais e de controle da
--                   integração (cursor, lotes, registros, fila, cadastros
--                   de campo e views de conciliação).
-- Execução ...: automática no primeiro boot do container Oracle, via sqlplus
--               conectado como SYSDBA. Como os objetos dos demais scripts são
--               criados com nome qualificado pelo SYSDBA, os schemas precisam
--               apenas de grant de conexão (menor privilégio).
-- Nota .......: senhas fixas e fictícias, válidas somente para a demo local.
--------------------------------------------------------------------------------
WHENEVER SQLERROR EXIT SQL.SQLCODE;

-- Schema do ERP fictício (referência cruzada com o "Projeto 1").
CREATE USER ERP_SUPRIMENTOS IDENTIFIED BY "ErpSuprimentosFicticio2026"
  DEFAULT TABLESPACE USERS
  QUOTA UNLIMITED ON USERS;

-- Schema do pipeline de integração (usado pelo integrador e pelo painel).
CREATE USER INTEGRACAO IDENTIFIED BY "IntegracaoFicticia2026"
  DEFAULT TABLESPACE USERS
  QUOTA UNLIMITED ON USERS;

-- Grants mínimos: apenas conexão.
GRANT CREATE SESSION TO ERP_SUPRIMENTOS;
GRANT CREATE SESSION TO INTEGRACAO;

EXIT;
