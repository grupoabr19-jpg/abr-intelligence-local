-- Migration: Central de Dados, Staging Layer, Fontes de Dados, Mapeamento e Rastreabilidade
-- Data: 2026-09-18
-- Idempotente com CREATE TABLE IF NOT EXISTS e ALTER TABLE ADD COLUMN IF NOT EXISTS

-- 1. Catálogo de Fontes de Dados
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 0. Tabelas base de negocio
CREATE TABLE IF NOT EXISTS public.clientes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_erp TEXT,
    nome TEXT,
    cnpj_cpf TEXT,
    cidade TEXT,
    uf TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.materiais (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo TEXT,
    descricao TEXT,
    tipo TEXT,
    especificacao TEXT,
    espessura TEXT,
    unidade_medida TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.depositos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo TEXT,
    nome TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.pedidos_venda (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_pv TEXT,
    data_emissao DATE,
    data_entrega DATE,
    status_geral TEXT,
    filial_origem TEXT,
    data_fechamento DATE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.itens_pedido (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pedido_id UUID REFERENCES public.pedidos_venda(id) ON DELETE SET NULL,
    material_id UUID REFERENCES public.materiais(id) ON DELETE SET NULL,
    quantidade_solicitada NUMERIC NOT NULL DEFAULT 0,
    quantidade_faturada NUMERIC NOT NULL DEFAULT 0,
    preco_unitario NUMERIC NOT NULL DEFAULT 0,
    unidade_medida TEXT,
    status_item TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.estoque (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_id UUID REFERENCES public.materiais(id) ON DELETE SET NULL,
    deposito_id UUID REFERENCES public.depositos(id) ON DELETE SET NULL,
    quantidade_total NUMERIC NOT NULL DEFAULT 0,
    quantidade_livre NUMERIC NOT NULL DEFAULT 0,
    quantidade_alocada NUMERIC NOT NULL DEFAULT 0,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.fornecedores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_erp TEXT,
    nome TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.precos_mercado (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_referencia DATE NOT NULL DEFAULT CURRENT_DATE,
    material_descricao TEXT,
    tipo_preco TEXT,
    valor NUMERIC NOT NULL DEFAULT 0,
    fonte TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.fontes_dados (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL CHECK (tipo IN ('API', 'webservice', 'banco_read_only', 'csv_upload', 'scraping', 'manual')),
    classificacao TEXT NOT NULL DEFAULT 'secundaria', -- 'primaria' (ERP Aster) ou 'secundaria' / 'mercado'
    status TEXT NOT NULL DEFAULT 'inativa' CHECK (status IN ('ativa', 'inativa', 'erro', 'sincronizando', 'standby')),
    frequencia_sincronizacao TEXT NOT NULL DEFAULT 'sob_demanda', -- 'tempo_real', 'diaria', 'semanal', 'mensal', 'sob_demanda'
    ultima_sincronizacao TIMESTAMPTZ,
    proxima_sincronizacao TIMESTAMPTZ,
    total_registros BIGINT NOT NULL DEFAULT 0,
    registros_erro BIGINT NOT NULL DEFAULT 0,
    url TEXT,
    secret_key_ref TEXT, -- Referência ao nome da variável/secret (NUNCA senha em texto plano)
    ambiente TEXT NOT NULL DEFAULT 'producao', -- 'testes', 'homologacao', 'producao'
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT true,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Tabela de Mapeamento de Campos (Fonte -> ABR Intelligence)
CREATE TABLE IF NOT EXISTS public.mapeamento_campos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fonte_id UUID NOT NULL REFERENCES public.fontes_dados(id) ON DELETE CASCADE,
    entidade_origem TEXT NOT NULL, -- Ex: 'CLIENTES', 'PEDIDOS', 'ESTOQUE'
    tabela_destino TEXT NOT NULL, -- Ex: 'clientes', 'pedidos_venda', 'itens_pedido', 'estoque'
    campo_origem TEXT NOT NULL, -- Ex: 'COD_CLIENTE', 'RAZAO_SOCIAL', 'PESO_LIQ'
    campo_destino TEXT NOT NULL, -- Ex: 'codigo_erp', 'nome', 'peso_unitario'
    tipo_transformacao TEXT NOT NULL DEFAULT 'direto', -- 'direto', 'converter_numero', 'converter_data', 'remover_pontuacao', 'maiusculo', 'json_extract'
    regra_transformacao TEXT,
    obrigatorio BOOLEAN NOT NULL DEFAULT false,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_mapeamento_campo UNIQUE (fonte_id, entidade_origem, campo_origem, tabela_destino, campo_destino)
);

-- 3. Histórico de Importações e Sincronizações
CREATE TABLE IF NOT EXISTS public.historico_importacoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_id TEXT NOT NULL,
    fonte_id UUID REFERENCES public.fontes_dados(id) ON DELETE SET NULL,
    entidade TEXT NOT NULL DEFAULT 'geral',
    iniciado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_em TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'processando' CHECK (status IN ('sucesso', 'parcial', 'erro', 'processando', 'abortado')),
    registros_lidos INTEGER NOT NULL DEFAULT 0,
    registros_inseridos INTEGER NOT NULL DEFAULT 0,
    registros_atualizados INTEGER NOT NULL DEFAULT 0,
    registros_erro INTEGER NOT NULL DEFAULT 0,
    duracao_ms INTEGER,
    usuario_id UUID REFERENCES auth.users(id),
    origem_arquivo TEXT,
    log TEXT,
    detalhes_erros JSONB DEFAULT '[]'::jsonb
);

-- 4. Camada de Staging (Staging Dados Genérica & Auditável por Entidade)
-- 3.1 Controle de uploads/importacoes pesadas
CREATE TABLE IF NOT EXISTS public.importacoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_arquivo TEXT NOT NULL,
    tamanho_bytes BIGINT NOT NULL DEFAULT 0,
    hash_arquivo TEXT NOT NULL UNIQUE,
    storage_path TEXT NOT NULL,
    sheet_path TEXT,
    fonte_id UUID REFERENCES public.fontes_dados(id) ON DELETE SET NULL,
    tipo_planilha TEXT NOT NULL DEFAULT 'desconhecido'
        CHECK (tipo_planilha IN ('desconhecido', 'GESTAO_PRODUCAO', 'MARGEM', 'CLIENTES', 'ESTOQUE', 'GERAL')),
    tipo_confirmado BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'recebido'
        CHECK (status IN ('recebido', 'processando', 'aguardando_aprovacao', 'promovido', 'erro')),
    linha_checkpoint INTEGER NOT NULL DEFAULT 0,
    linhas_total INTEGER,
    linhas_validas INTEGER NOT NULL DEFAULT 0,
    linhas_erro INTEGER NOT NULL DEFAULT 0,
    linhas_duplicadas INTEGER NOT NULL DEFAULT 0,
    erro_mensagem TEXT,
    entidade TEXT,
    sync_id TEXT,
    usuario_id UUID REFERENCES auth.users(id),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.staging_dados (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fonte_id UUID REFERENCES public.fontes_dados(id) ON DELETE SET NULL,
    source_system TEXT NOT NULL DEFAULT 'manual', -- 'ASTER_ERP', 'UPLOAD_MANUAL', 'ACO_BRASIL', etc.
    source_id TEXT, -- ID ou chave original no sistema emissor
    entidade TEXT NOT NULL, -- 'clientes', 'produtos', 'pedidos_venda', 'itens_pedido', 'estoque', 'fornecedores', 'notas_fiscais'
    payload_original JSONB NOT NULL, -- Preserva 100% o payload original sem perda
    dados_transformados JSONB, -- Dados já mapeados para as colunas de destino
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sync_id TEXT NOT NULL,
    hash_registro TEXT NOT NULL, -- MD5 ou SHA-256 do payload para idempotência
    status_validacao TEXT NOT NULL DEFAULT 'pendente' CHECK (status_validacao IN ('pendente', 'valido', 'invalido', 'processado', 'erro')),
    erro_validacao TEXT,
    tabela_destino TEXT,
    registro_destino_id UUID, -- UUID do registro gerado/atualizado na tabela principal
    ativo BOOLEAN NOT NULL DEFAULT true
);

-- 5. Tabela de Indicadores Econômicos (dólar, minério de ferro, sucata, frete)
CREATE TABLE IF NOT EXISTS public.indicadores_economicos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_referencia DATE NOT NULL,
    indicador TEXT NOT NULL, -- 'dolar_ptax', 'dolar_comercial', 'minerio_ferro_62', 'sucata_ferrosa', 'frete_medio_ton'
    valor NUMERIC NOT NULL,
    unidade TEXT NOT NULL DEFAULT 'R$', -- 'R$', 'US$', 'US$/t', 'R$/t'
    variacao_percent NUMERIC DEFAULT 0,
    fonte TEXT NOT NULL, -- 'Banco Central do Brasil', 'Fastmarkets', 'S&P Global Platts', 'ANTT'
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_indicador_data_fonte UNIQUE (indicador, data_referencia, fonte)
);

-- 6. Adicionar colunas de rastreabilidade nas tabelas principais
-- (source_system, source_id, sync_id, hash_registro, ativo)
ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS hash_registro TEXT;
ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT true;

ALTER TABLE public.materiais ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.materiais ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.materiais ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.materiais ADD COLUMN IF NOT EXISTS hash_registro TEXT;
ALTER TABLE public.materiais ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT true;

ALTER TABLE public.depositos ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.depositos ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.depositos ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.depositos ADD COLUMN IF NOT EXISTS hash_registro TEXT;
ALTER TABLE public.depositos ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT true;

ALTER TABLE public.pedidos_venda ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.pedidos_venda ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.pedidos_venda ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.pedidos_venda ADD COLUMN IF NOT EXISTS hash_registro TEXT;
ALTER TABLE public.pedidos_venda ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT true;

ALTER TABLE public.itens_pedido ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.itens_pedido ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.itens_pedido ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.itens_pedido ADD COLUMN IF NOT EXISTS hash_registro TEXT;
ALTER TABLE public.itens_pedido ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT true;

ALTER TABLE public.estoque ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.estoque ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.estoque ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.estoque ADD COLUMN IF NOT EXISTS hash_registro TEXT;
ALTER TABLE public.estoque ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT true;

ALTER TABLE public.fornecedores ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.fornecedores ADD COLUMN IF NOT EXISTS source_id TEXT;
ALTER TABLE public.fornecedores ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.fornecedores ADD COLUMN IF NOT EXISTS hash_registro TEXT;

ALTER TABLE public.precos_mercado ADD COLUMN IF NOT EXISTS commodity TEXT;
ALTER TABLE public.precos_mercado ADD COLUMN IF NOT EXISTS unidade TEXT DEFAULT 'R$/t';
ALTER TABLE public.precos_mercado ADD COLUMN IF NOT EXISTS source_system TEXT DEFAULT 'demonstracao';
ALTER TABLE public.precos_mercado ADD COLUMN IF NOT EXISTS sync_id TEXT;
ALTER TABLE public.precos_mercado ADD COLUMN IF NOT EXISTS hash_registro TEXT;

-- Índices de busca e rastreabilidade
CREATE INDEX IF NOT EXISTS idx_staging_sync_id ON public.staging_dados(sync_id);
CREATE INDEX IF NOT EXISTS idx_staging_source ON public.staging_dados(source_system, source_id);
CREATE INDEX IF NOT EXISTS idx_staging_hash ON public.staging_dados(hash_registro);
CREATE INDEX IF NOT EXISTS idx_staging_status ON public.staging_dados(status_validacao);
CREATE INDEX IF NOT EXISTS idx_historico_sync_id ON public.historico_importacoes(sync_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_historico_importacoes_sync_id ON public.historico_importacoes(sync_id);
CREATE INDEX IF NOT EXISTS idx_historico_fonte ON public.historico_importacoes(fonte_id);
CREATE INDEX IF NOT EXISTS idx_indicadores_data ON public.indicadores_economicos(data_referencia, indicador);
CREATE INDEX IF NOT EXISTS idx_importacoes_status ON public.importacoes(status, criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_importacoes_fonte ON public.importacoes(fonte_id);

-- 7. RLS Policies
ALTER TABLE public.fontes_dados ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mapeamento_campos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.historico_importacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.importacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.staging_dados ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.indicadores_economicos ENABLE ROW LEVEL SECURITY;

-- Fontes de Dados
DROP POLICY IF EXISTS "fontes_dados_auth_select" ON public.fontes_dados;
CREATE POLICY "fontes_dados_auth_select" ON public.fontes_dados
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "fontes_dados_auth_insert" ON public.fontes_dados;
CREATE POLICY "fontes_dados_auth_insert" ON public.fontes_dados
    FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "fontes_dados_auth_update" ON public.fontes_dados;
CREATE POLICY "fontes_dados_auth_update" ON public.fontes_dados
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "fontes_dados_auth_delete" ON public.fontes_dados;
CREATE POLICY "fontes_dados_auth_delete" ON public.fontes_dados
    FOR DELETE TO authenticated USING (true);

-- Mapeamento de Campos
DROP POLICY IF EXISTS "mapeamento_campos_auth_select" ON public.mapeamento_campos;
CREATE POLICY "mapeamento_campos_auth_select" ON public.mapeamento_campos
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "mapeamento_campos_auth_insert" ON public.mapeamento_campos;
CREATE POLICY "mapeamento_campos_auth_insert" ON public.mapeamento_campos
    FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "mapeamento_campos_auth_update" ON public.mapeamento_campos;
CREATE POLICY "mapeamento_campos_auth_update" ON public.mapeamento_campos
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "mapeamento_campos_auth_delete" ON public.mapeamento_campos;
CREATE POLICY "mapeamento_campos_auth_delete" ON public.mapeamento_campos
    FOR DELETE TO authenticated USING (true);

-- Histórico de Importações
DROP POLICY IF EXISTS "historico_importacoes_auth_select" ON public.historico_importacoes;
CREATE POLICY "historico_importacoes_auth_select" ON public.historico_importacoes
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "historico_importacoes_auth_insert" ON public.historico_importacoes;
CREATE POLICY "historico_importacoes_auth_insert" ON public.historico_importacoes
    FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "historico_importacoes_auth_update" ON public.historico_importacoes;
CREATE POLICY "historico_importacoes_auth_update" ON public.historico_importacoes
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "historico_importacoes_auth_delete" ON public.historico_importacoes;
CREATE POLICY "historico_importacoes_auth_delete" ON public.historico_importacoes
    FOR DELETE TO authenticated USING (true);

-- Importacoes
DROP POLICY IF EXISTS "importacoes_auth_select" ON public.importacoes;
CREATE POLICY "importacoes_auth_select" ON public.importacoes
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "importacoes_auth_insert" ON public.importacoes;
CREATE POLICY "importacoes_auth_insert" ON public.importacoes
    FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "importacoes_auth_update" ON public.importacoes;
CREATE POLICY "importacoes_auth_update" ON public.importacoes
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "importacoes_auth_delete" ON public.importacoes;
CREATE POLICY "importacoes_auth_delete" ON public.importacoes
    FOR DELETE TO authenticated USING (true);

-- Staging Dados
DROP POLICY IF EXISTS "staging_dados_auth_select" ON public.staging_dados;
CREATE POLICY "staging_dados_auth_select" ON public.staging_dados
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "staging_dados_auth_insert" ON public.staging_dados;
CREATE POLICY "staging_dados_auth_insert" ON public.staging_dados
    FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "staging_dados_auth_update" ON public.staging_dados;
CREATE POLICY "staging_dados_auth_update" ON public.staging_dados
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "staging_dados_auth_delete" ON public.staging_dados;
CREATE POLICY "staging_dados_auth_delete" ON public.staging_dados
    FOR DELETE TO authenticated USING (true);

-- Indicadores Econômicos
DROP POLICY IF EXISTS "indicadores_economicos_auth_select" ON public.indicadores_economicos;
CREATE POLICY "indicadores_economicos_auth_select" ON public.indicadores_economicos
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "indicadores_economicos_auth_insert" ON public.indicadores_economicos;
CREATE POLICY "indicadores_economicos_auth_insert" ON public.indicadores_economicos
    FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "indicadores_economicos_auth_update" ON public.indicadores_economicos;
CREATE POLICY "indicadores_economicos_auth_update" ON public.indicadores_economicos
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "indicadores_economicos_auth_delete" ON public.indicadores_economicos;
CREATE POLICY "indicadores_economicos_auth_delete" ON public.indicadores_economicos
    FOR DELETE TO authenticated USING (true);

-- 8. Seed Inicial de Fontes de Dados
INSERT INTO public.fontes_dados (
    id, nome, tipo, classificacao, status, frequencia_sincronizacao, url, secret_key_ref, ambiente, descricao, total_registros, registros_erro
) VALUES 
(
    'a0000000-0000-4000-8000-000000000001'::uuid,
    'ASTER ERP (SPS Group)',
    'API',
    'primaria',
    'inativa',
    'diaria',
    'https://aster.gruposps.com.br/Login/abr',
    'ASTER_API_TOKEN',
    'testes',
    'ERP corporativo principal do Grupo ABR (SPS Group). Aguardando liberação de credenciais técnicas pela SPS Group.',
    0,
    0
),
(
    'a0000000-0000-4000-8000-000000000002'::uuid,
    'Aço Brasil (IABr)',
    'scraping',
    'mercado',
    'inativa',
    'mensal',
    'https://acobrasil.org.br/estatisticas',
    NULL,
    'producao',
    'Fonte pública do Instituto Aço Brasil com dados setoriais mensais de produção, vendas internas e consumo aparente.',
    0,
    0
),
(
    'a0000000-0000-4000-8000-000000000003'::uuid,
    'Worldsteel Association',
    'scraping',
    'mercado',
    'inativa',
    'mensal',
    'https://worldsteel.org/steel-by-topic/statistics',
    NULL,
    'producao',
    'Associação Mundial do Aço com séries históricas globais de produção por polo (China, Índia, EUA, Europa e Brasil).',
    0,
    0
),
(
    'a0000000-0000-4000-8000-000000000004'::uuid,
    'Fastmarkets',
    'webservice',
    'mercado',
    'inativa',
    'semanal',
    'https://www.fastmarkets.com/commodities/steel',
    'FASTMARKETS_API_KEY',
    'producao',
    'Fonte paga de inteligência de preços e índices internacionais de bobinas laminadas a quente, fio-máquina e sucata.',
    0,
    0
),
(
    'a0000000-0000-4000-8000-000000000005'::uuid,
    'Upload Manual (CSV / Planilha)',
    'csv_upload',
    'primaria',
    'ativa',
    'sob_demanda',
    NULL,
    NULL,
    'producao',
    'Mecanismo de importação manual auditado com validação por staging e normalização via mapeamento de campos.',
    0,
    0
)
ON CONFLICT (id) DO UPDATE SET
    nome = EXCLUDED.nome,
    tipo = EXCLUDED.tipo,
    classificacao = EXCLUDED.classificacao,
    url = EXCLUDED.url,
    descricao = EXCLUDED.descricao;

-- 9. Seed Inicial de Mapeamento de Campos (Exemplos pré-cadastrados do diagnóstico)
INSERT INTO public.mapeamento_campos (
    fonte_id, entidade_origem, tabela_destino, campo_origem, campo_destino, tipo_transformacao, obrigatorio, regra_transformacao
) VALUES
-- Clientes
('a0000000-0000-4000-8000-000000000001'::uuid, 'CLIENTES', 'clientes', 'COD_CLIENTE', 'codigo_erp', 'direto', true, 'Chave única de identificação no ERP'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'CLIENTES', 'clientes', 'RAZAO_SOCIAL', 'nome', 'direto', true, 'Razão social / nome fantasia'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'CLIENTES', 'clientes', 'CNPJ_CPF', 'cnpj_cpf', 'remover_pontuacao', true, 'Apenas dígitos'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'CLIENTES', 'clientes', 'CIDADE', 'cidade', 'maiusculo', false, 'Normalizar caixa alta'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'CLIENTES', 'clientes', 'UF_ESTADO', 'uf', 'maiusculo', false, 'Sigla do estado'),

-- Pedidos de Venda
('a0000000-0000-4000-8000-000000000001'::uuid, 'PEDIDOS', 'pedidos_venda', 'NUM_PEDIDO', 'numero_pv', 'direto', true, 'Número oficial do pedido de venda'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'PEDIDOS', 'pedidos_venda', 'DT_EMISSAO', 'data_emissao', 'converter_data', true, 'Formato ISO YYYY-MM-DD'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'PEDIDOS', 'pedidos_venda', 'DT_ENTREGA', 'data_entrega', 'converter_data', false, 'Previsão de entrega'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'PEDIDOS', 'pedidos_venda', 'STATUS_PED', 'status_geral', 'direto', false, 'Status operacional'),

-- Itens do Pedido
('a0000000-0000-4000-8000-000000000001'::uuid, 'ITENS_PEDIDO', 'itens_pedido', 'PESO_LIQ', 'quantidade_solicitada', 'converter_numero', true, 'Peso em kg solicitado'),
('a0000000-0000-4000-8000-000000000001'::uuid, 'ITENS_PEDIDO', 'itens_pedido', 'VALOR_TOTAL', 'preco_unitario', 'converter_numero', true, 'Preço por kg em R$'),

-- Upload Manual (Mapeamentos flexíveis)
('a0000000-0000-4000-8000-000000000005'::uuid, 'CLIENTES', 'clientes', 'COD_CLIENTE', 'codigo_erp', 'direto', true, 'Código ERP ABR'),
('a0000000-0000-4000-8000-000000000005'::uuid, 'CLIENTES', 'clientes', 'RAZAO_SOCIAL', 'nome', 'direto', true, 'Nome do cliente'),
('a0000000-0000-4000-8000-000000000005'::uuid, 'CLIENTES', 'clientes', 'CNPJ_CPF', 'cnpj_cpf', 'remover_pontuacao', false, 'Documento'),
('a0000000-0000-4000-8000-000000000005'::uuid, 'PEDIDOS', 'pedidos_venda', 'NUM_PEDIDO', 'numero_pv', 'direto', true, 'Número do PV'),
('a0000000-0000-4000-8000-000000000005'::uuid, 'PEDIDOS', 'pedidos_venda', 'DT_EMISSAO', 'data_emissao', 'converter_data', true, 'Data de emissão'),
('a0000000-0000-4000-8000-000000000005'::uuid, 'ESTOQUE', 'estoque', 'QTD_TOTAL', 'quantidade_total', 'converter_numero', true, 'Estoque físico em toneladas')
ON CONFLICT (fonte_id, entidade_origem, campo_origem, tabela_destino, campo_destino) DO NOTHING;

-- 10. Seed Inicial de Indicadores Econômicos de Mercado
INSERT INTO public.indicadores_economicos (
    data_referencia, indicador, valor, unidade, variacao_percent, fonte
) VALUES
('2026-09-18', 'dolar_ptax', 5.3420, 'R$', -0.35, 'Banco Central do Brasil'),
('2026-09-18', 'minerio_ferro_62', 104.50, 'US$/t', +1.20, 'Fastmarkets / Dalian'),
('2026-09-18', 'sucata_ferrosa', 1450.00, 'R$/t', +0.80, 'Mercado Doméstico / IABr'),
('2026-09-18', 'frete_medio_ton', 185.00, 'R$/t', +0.40, 'ANTT / Sifreca')
ON CONFLICT (indicador, data_referencia, fonte) DO NOTHING;

-- 11. Seed de Séries de Preços de Mercado por Commodity (BQ, Galvanizado, Vergalhão)
INSERT INTO public.precos_mercado (
    data_referencia, material_descricao, commodity, tipo_preco, valor, unidade, fonte, source_system
) VALUES
('2026-09-15', 'Bobina Laminada a Quente (BQ)', 'BQ', 'distribuidor', 5850.00, 'R$/t', 'Fastmarkets', 'mercado_externo'),
('2026-09-15', 'Chapa Galvanizada Z275', 'Galvanizado', 'distribuidor', 6420.00, 'R$/t', 'Fastmarkets', 'mercado_externo'),
('2026-09-15', 'Vergalhão CA-50 10mm', 'Vergalhão', 'distribuidor', 5100.00, 'R$/t', 'Aço Brasil', 'mercado_externo'),
('2026-08-15', 'Bobina Laminada a Quente (BQ)', 'BQ', 'distribuidor', 5790.00, 'R$/t', 'Fastmarkets', 'mercado_externo'),
('2026-08-15', 'Chapa Galvanizada Z275', 'Galvanizado', 'distribuidor', 6380.00, 'R$/t', 'Fastmarkets', 'mercado_externo'),
('2026-08-15', 'Vergalhão CA-50 10mm', 'Vergalhão', 'distribuidor', 5150.00, 'R$/t', 'Aço Brasil', 'mercado_externo')
ON CONFLICT DO NOTHING;
