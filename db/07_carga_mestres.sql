--------------------------------------------------------------------------------
-- Projeto 2 (demo fictícia) — Integração Sistema de Campo → ERP
--
-- Arquivo ....: 07_carga_mestres.sql
-- Tarefa .....: 1.8 — Carga de dados mestres fictícios
-- Objetivo ...: Popular os cadastros da demo (sem dados reais ou marcas de
--               terceiros):
--                 * TALHAO     : TAL-001 … TAL-018 ativos; TAL-019/TAL-020
--                                INATIVOS (ativo = 0).
--                 * EQUIPAMENTO: EQP-001 … EQP-014 ativos; EQP-015 inativo.
--                 * ITEM       : ITEM-001 … ITEM-010 (ERP_SUPRIMENTOS —
--                                referência cruzada com o "Projeto 1"
--                                fictício, mantido autocontido nesta demo).
--                 * INT_CURSOR : semeia o cursor 'CAMPO_API' com a posição
--                                sentinela '1970-01-01T00:00:00Z'
--                                (= "integrar desde o início").
-- Nota .......: os `id` não são informados (IDENTITY os gera em 1..N pela
--               ordem de inserção); a chave de negócio é o `codigo`.
--------------------------------------------------------------------------------
SET DEFINE OFF;
WHENEVER SQLERROR EXIT SQL.SQLCODE;

-- ---------------------------------------------------------------------------
-- TALHAO (20 parcelas fictícias)
-- ---------------------------------------------------------------------------
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-001', 'Talhão Fazenda Boa Vista — Setor Norte', 120.50, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-002', 'Talhão Fazenda Boa Vista — Setor Sul', 85.20, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-003', 'Talhão Fazenda Boa Vista — Setor Leste', 96.75, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-004', 'Talhão Fazenda São Luiz — Setor Norte', 150.00, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-005', 'Talhão Fazenda São Luiz — Setor Sul', 74.30, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-006', 'Talhão Fazenda Santa Clara — Setor Central', 210.40, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-007', 'Talhão Fazenda Santa Clara — Setor Leste', 132.80, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-008', 'Talhão Fazenda Recanto — Setor Norte', 58.90, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-009', 'Talhão Fazenda Recanto — Setor Oeste', 64.15, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-010', 'Talhão Fazenda Boa Esperança — Setor Norte', 175.60, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-011', 'Talhão Fazenda Boa Esperança — Setor Sul', 201.35, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-012', 'Talhão Fazenda Boa Esperança — Setor Oeste', 88.45, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-013', 'Talhão Fazenda Vale Verde — Setor Norte', 143.70, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-014', 'Talhão Fazenda Vale Verde — Setor Sul', 92.60, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-015', 'Talhão Fazenda Vale do Sol — Setor Leste', 118.25, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-016', 'Talhão Fazenda Vale do Sol — Setor Oeste', 79.90, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-017', 'Talhão Fazenda Horizonte Azul — Setor Norte', 236.10, 1);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-018', 'Talhão Fazenda Horizonte Azul — Setor Sul', 105.55, 1);
-- Cadastros INATIVOS (devem ser rejeitados pela validação do integrador).
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-019', 'Talhão Fazenda Horizonte Azul — Setor Baixada', 47.00, 0);
INSERT INTO INTEGRACAO.TALHAO (codigo, descricao, area_ha, ativo) VALUES
  ('TAL-020', 'Talhão Fazenda Boa Vista — Área Experimental', 33.80, 0);

-- ---------------------------------------------------------------------------
-- EQUIPAMENTO (15 máquinas/veículos fictícios)
-- ---------------------------------------------------------------------------
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-001', 'Trator de média potência — Frota Principal', 'TRATOR', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-002', 'Trator de alta potência — Frota Principal', 'TRATOR', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-003', 'Trator compacto — Frota Auxiliar', 'TRATOR', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-004', 'Trator de esteiras — Preparo de Solo', 'TRATOR', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-005', 'Colhedora de grãos — Frota Principal', 'COLHEDORA', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-006', 'Colhedora de grãos — Frota Auxiliar', 'COLHEDORA', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-007', 'Colhedora especial — Frente Norte', 'COLHEDORA', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-008', 'Caminhão baú — Transporte de Grãos', 'CAMINHAO', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-009', 'Caminhão caçamba — Manutenção de Estradas', 'CAMINHAO', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-010', 'Caminhão tanque — Abastecimento de Campo', 'CAMINHAO', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-011', 'Pulverizador autopropelido — Frota Principal', 'PULVERIZADOR', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-012', 'Pulverizador de arrasto — Frota Auxiliar', 'PULVERIZADOR', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-013', 'Plantadeira de precisão — Safrinha', 'OUTRO', 1);
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-014', 'Carreta agrícola — Transporte de Insumos', 'OUTRO', 1);
-- Cadastro INATIVO (deve ser rejeitado pela validação do integrador).
INSERT INTO INTEGRACAO.EQUIPAMENTO (codigo, descricao, tipo, ativo) VALUES
  ('EQP-015', 'Colhedora antiga — Baixa Programada', 'COLHEDORA', 0);

-- ---------------------------------------------------------------------------
-- ITEM (10 insumos/produtos fictícios do ERP_SUPRIMENTOS — "Projeto 1")
-- ---------------------------------------------------------------------------
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-001', 'Adubo NPK formulação fictícia 20-05-20', 'KG', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-002', 'Calcário agrícola moído', 'KG', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-003', 'Semente de milho híbrido — demo', 'SC', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-004', 'Semente de soja — demo', 'SC', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-005', 'Herbicida genérico de pré-plantio', 'L', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-006', 'Fungicida genérico multiuso', 'L', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-007', 'Inseticida genérico de largo espectro', 'L', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-008', 'Óleo lubrificante agrícola', 'L', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-009', 'Diesel fictício — Posto Interno', 'L', 1);
INSERT INTO ERP_SUPRIMENTOS.ITEM (codigo, descricao, unidade, ativo) VALUES
  ('ITEM-010', 'Peça de reposição genérica — Filtro', 'UN', 1);

-- ---------------------------------------------------------------------------
-- INT_CURSOR (semente do cursor da API do sistema de campo simulado)
-- ---------------------------------------------------------------------------
INSERT INTO INTEGRACAO.INT_CURSOR (nome, posicao) VALUES
  ('CAMPO_API', '1970-01-01T00:00:00Z');

-- DML exige COMMIT explícito (sqlplus não faz autocommit).
COMMIT;

EXIT;
