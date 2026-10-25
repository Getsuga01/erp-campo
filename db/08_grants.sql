--------------------------------------------------------------------------------
-- Projeto 2 (demo fictícia) — Integração Sistema de Campo → ERP
--
-- Arquivo ....: 08_grants.sql
-- Tarefa .....: 1.9 — Grants entre schemas
-- Objetivo ...: Conceder ao schema INTEGRACAO (integrador e painel) o acesso
--               mínimo necessário aos objetos do ERP fictício:
--                 * SELECT em ITEM               — validar insumos nos
--                   apontamentos do tipo INSUMO.
--                 * SELECT/INSERT em
--                   APONTAMENTO_CAMPO           — gravar os apontamentos
--                   validados e conferir o destino.
--               Os objetos de INTEGRACAO (cursor, lotes, registros, fila e
--               views) já pertencem ao próprio schema — não exigem grants.
-- Cruzamento com o "Projeto 1" (fictício): ERP_SUPRIMENTOS representa o ERP do
-- Projeto 1 de forma autocontida nesta demo; ITEM é o cadastro compartilhado.
-- Numa instalação real, este grant seria dado pelo schema oficial do ERP.
--------------------------------------------------------------------------------
WHENEVER SQLERROR EXIT SQL.SQLCODE;

-- Objetos da demo vivem no PDB XEPDB1 (ver 01_schema.sql); cada script roda
-- em sessão sqlplus nova conectada ao CDB$ROOT — trocar de container aqui.
ALTER SESSION SET CONTAINER = XEPDB1;

GRANT SELECT ON ERP_SUPRIMENTOS.ITEM TO INTEGRACAO;
GRANT SELECT, INSERT ON ERP_SUPRIMENTOS.APONTAMENTO_CAMPO TO INTEGRACAO;

EXIT;
