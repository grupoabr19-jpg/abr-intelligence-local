create extension if not exists pgcrypto;

create table if not exists public.mercado_fontes (
  source_key text primary key,
  nome text not null,
  tipo text not null check (tipo in ('api', 'html', 'download', 'csv', 'parquet', 'microdados')),
  categoria text not null default 'mercado',
  url_base text,
  url_documentacao text,
  frequencia text not null default 'mensal',
  ativo boolean not null default true,
  configuracao jsonb not null default '{}'::jsonb,
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.mercado_coletas (
  id uuid primary key default gen_random_uuid(),
  source_key text not null references public.mercado_fontes(source_key) on delete cascade,
  status text not null default 'processando' check (status in ('processando', 'sucesso', 'parcial', 'erro')),
  iniciado_em timestamptz not null default now(),
  finalizado_em timestamptz,
  registros_encontrados integer not null default 0,
  registros_inseridos integer not null default 0,
  erro text,
  metadados jsonb not null default '{}'::jsonb
);

create table if not exists public.mercado_documentos (
  id uuid primary key default gen_random_uuid(),
  source_key text not null references public.mercado_fontes(source_key) on delete cascade,
  coleta_id uuid references public.mercado_coletas(id) on delete set null,
  tipo_documento text not null default 'pagina',
  titulo text,
  url text not null,
  periodo_label text,
  publicado_em date,
  hash_conteudo text,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now(),
  constraint uq_mercado_documentos_source_url unique (source_key, url)
);

create table if not exists public.mercado_indicadores (
  id uuid primary key default gen_random_uuid(),
  source_key text not null references public.mercado_fontes(source_key) on delete cascade,
  documento_id uuid references public.mercado_documentos(id) on delete set null,
  indicador_key text not null,
  indicador_nome text not null,
  periodo_inicio date,
  periodo_fim date,
  periodo_label text,
  geografia text not null default 'BR',
  unidade text,
  valor numeric,
  valor_texto text,
  dimensoes jsonb not null default '{}'::jsonb,
  payload_original jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create index if not exists mercado_coletas_source_started_idx
  on public.mercado_coletas (source_key, iniciado_em desc);

create index if not exists mercado_documentos_source_collected_idx
  on public.mercado_documentos (source_key, coletado_em desc);

create index if not exists mercado_indicadores_key_period_idx
  on public.mercado_indicadores (indicador_key, periodo_inicio, periodo_fim);

create unique index if not exists uq_mercado_indicadores_grain
  on public.mercado_indicadores (
    source_key,
    indicador_key,
    coalesce(periodo_inicio, date '0001-01-01'),
    coalesce(periodo_fim, date '0001-01-01'),
    geografia,
    md5(dimensoes::text)
  );

alter table public.mercado_fontes enable row level security;
alter table public.mercado_coletas enable row level security;
alter table public.mercado_documentos enable row level security;
alter table public.mercado_indicadores enable row level security;

drop policy if exists mercado_fontes_read_public on public.mercado_fontes;
create policy mercado_fontes_read_public
  on public.mercado_fontes
  for select
  to anon, authenticated
  using (true);

drop policy if exists mercado_coletas_read_public on public.mercado_coletas;
create policy mercado_coletas_read_public
  on public.mercado_coletas
  for select
  to anon, authenticated
  using (true);

drop policy if exists mercado_documentos_read_public on public.mercado_documentos;
create policy mercado_documentos_read_public
  on public.mercado_documentos
  for select
  to anon, authenticated
  using (true);

drop policy if exists mercado_indicadores_read_public on public.mercado_indicadores;
create policy mercado_indicadores_read_public
  on public.mercado_indicadores
  for select
  to anon, authenticated
  using (true);

grant select on public.mercado_fontes to anon, authenticated;
grant select on public.mercado_coletas to anon, authenticated;
grant select on public.mercado_documentos to anon, authenticated;
grant select on public.mercado_indicadores to anon, authenticated;

insert into public.mercado_fontes(source_key, nome, tipo, categoria, url_base, url_documentacao, frequencia, configuracao, observacoes)
values
  ('bcb_dolar_ptax', 'BCB dolar PTAX', 'api', 'macro', 'https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata', 'https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/documentacao', 'diaria', '{"env_base_url": "BCB_DOLAR_API_BASE_URL"}'::jsonb, 'API publica OData, sem token.'),
  ('ibge_pim_sidra', 'IBGE PIM SIDRA', 'api', 'industria', 'https://apisidra.ibge.gov.br/values', 'https://apisidra.ibge.gov.br/DescritoresTabela/t', 'mensal', '{"env_values_url": "IBGE_SIDRA_VALUES_BASE_URL", "env_descriptor_url": "IBGE_SIDRA_DESCRIPTOR_BASE_URL"}'::jsonb, 'API publica SIDRA, sem token.'),
  ('aco_brasil_estatistica_mensal', 'Aco Brasil estatistica mensal', 'html', 'aco', 'https://www.acobrasil.org.br/site/estatistica-mensal/', null, 'mensal', '{"env_page_url": "ACO_BRASIL_PAGE_URL"}'::jsonb, 'Pagina publica com links de download das estatisticas mensais.'),
  ('cni_sondagem_industrial', 'CNI sondagem industrial', 'html', 'industria', 'https://www.portaldaindustria.com.br/estatisticas/sondagem-industrial/', null, 'mensal', '{"env_page_url": "CNI_INDUSTRIA_PAGE_URL"}'::jsonb, 'Pagina publica de sondagem industrial.'),
  ('cni_sondagem_construcao', 'CNI sondagem industria da construcao', 'html', 'construcao', 'https://www.portaldaindustria.com.br/estatisticas/sondagem-industria-da-construcao/', null, 'mensal', '{"env_page_url": "CNI_CONSTRUCAO_PAGE_URL"}'::jsonb, 'Pagina publica de sondagem da construcao.'),
  ('inda_estatisticas', 'INDA estatisticas', 'html', 'aco', 'https://www.inda.org.br/estatisticas/', null, 'mensal', '{"env_page_url": "INDA_PAGE_URL"}'::jsonb, 'Pagina publica de estatisticas do INDA.')
on conflict (source_key)
do update set
  nome = excluded.nome,
  tipo = excluded.tipo,
  categoria = excluded.categoria,
  url_base = excluded.url_base,
  url_documentacao = excluded.url_documentacao,
  frequencia = excluded.frequencia,
  configuracao = excluded.configuracao,
  observacoes = excluded.observacoes,
  atualizado_em = now();
