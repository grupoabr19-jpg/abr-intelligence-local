create table if not exists public.dim_cnae_abr (
  cnae text primary key,
  descricao text not null,
  categoria_abr text not null check (categoria_abr in ('CONSTRUCAO', 'METALURGIA', 'PRODUTOS_DE_METAL', 'MAQUINAS_EQUIPAMENTOS', 'INDUSTRIA_CONSUMIDORA', 'OUTRAS')),
  ativo boolean not null default true,
  vigencia_inicio date,
  vigencia_fim date,
  validado_por text,
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.pncp_modality_codes (
  codigo text primary key,
  descricao text not null,
  ativo boolean not null default true,
  validado_por text,
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.raw_caged (
  id bigserial primary key,
  ano_mes text not null,
  municipio text,
  cnae text not null,
  admissoes integer not null default 0,
  desligamentos integer not null default 0,
  saldo integer not null default 0,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create table if not exists public.fact_employment_monthly (
  id bigserial primary key,
  periodo_inicio date not null,
  municipio text,
  cnae text not null references public.dim_cnae_abr(cnae),
  categoria_abr text not null,
  admissoes integer not null default 0,
  desligamentos integer not null default 0,
  saldo integer not null default 0,
  coletado_em timestamptz not null default now()
);

create table if not exists public.raw_pncp (
  id bigserial primary key,
  pncp_id text not null,
  data_publicacao date,
  modalidade_codigo text,
  orgao text,
  municipio text,
  uf text,
  objeto text,
  valor_estimado numeric,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now(),
  unique (pncp_id)
);

create table if not exists public.fact_pncp_opportunities (
  id bigserial primary key,
  pncp_id text not null,
  data_publicacao date,
  modalidade_codigo text,
  orgao text,
  municipio text,
  uf text,
  objeto text,
  valor_estimado numeric,
  relevance_score integer not null default 0,
  termos_encontrados jsonb not null default '[]'::jsonb,
  payload_original jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now(),
  unique (pncp_id)
);

create index if not exists fact_employment_monthly_period_category_idx
  on public.fact_employment_monthly (periodo_inicio desc, categoria_abr);

create unique index if not exists uq_raw_caged_grain
  on public.raw_caged (ano_mes, coalesce(municipio, ''), cnae);

create unique index if not exists uq_fact_employment_monthly_grain
  on public.fact_employment_monthly (periodo_inicio, coalesce(municipio, ''), cnae);

create index if not exists fact_pncp_opportunities_date_score_idx
  on public.fact_pncp_opportunities (data_publicacao desc, relevance_score desc);

alter table public.dim_cnae_abr enable row level security;
alter table public.pncp_modality_codes enable row level security;
alter table public.raw_caged enable row level security;
alter table public.fact_employment_monthly enable row level security;
alter table public.raw_pncp enable row level security;
alter table public.fact_pncp_opportunities enable row level security;

drop policy if exists dim_cnae_abr_read_public on public.dim_cnae_abr;
create policy dim_cnae_abr_read_public on public.dim_cnae_abr for select to anon, authenticated using (true);

drop policy if exists pncp_modality_codes_read_public on public.pncp_modality_codes;
create policy pncp_modality_codes_read_public on public.pncp_modality_codes for select to anon, authenticated using (true);

drop policy if exists raw_caged_read_public on public.raw_caged;
create policy raw_caged_read_public on public.raw_caged for select to anon, authenticated using (true);

drop policy if exists fact_employment_monthly_read_public on public.fact_employment_monthly;
create policy fact_employment_monthly_read_public on public.fact_employment_monthly for select to anon, authenticated using (true);

drop policy if exists raw_pncp_read_public on public.raw_pncp;
create policy raw_pncp_read_public on public.raw_pncp for select to anon, authenticated using (true);

drop policy if exists fact_pncp_opportunities_read_public on public.fact_pncp_opportunities;
create policy fact_pncp_opportunities_read_public on public.fact_pncp_opportunities for select to anon, authenticated using (true);

grant select on public.dim_cnae_abr to anon, authenticated;
grant select on public.pncp_modality_codes to anon, authenticated;
grant select on public.raw_caged to anon, authenticated;
grant select on public.fact_employment_monthly to anon, authenticated;
grant select on public.raw_pncp to anon, authenticated;
grant select on public.fact_pncp_opportunities to anon, authenticated;

insert into public.mercado_fontes(source_key, nome, tipo, categoria, url_base, frequencia, configuracao, observacoes)
values
  ('caged_microdados', 'CAGED microdados', 'microdados', 'trabalho', 'ftp://ftp.mtps.gov.br/pdet/microdados/', 'mensal', '{"env_base_url": "CAGED_MICRODADOS_BASE_URL"}'::jsonb, 'Microdados publicos. Exige dim_cnae_abr aprovada antes de processar.'),
  ('pncp_consulta', 'PNCP consulta', 'api', 'governo', 'https://pncp.gov.br/api/consulta/v1', 'diaria', '{"env_base_url": "PNCP_API_BASE_URL"}'::jsonb, 'API publica. Exige pncp_modality_codes aprovadas antes de consultar oportunidades.')
on conflict (source_key)
do update set
  nome = excluded.nome,
  tipo = excluded.tipo,
  categoria = excluded.categoria,
  url_base = excluded.url_base,
  frequencia = excluded.frequencia,
  configuracao = excluded.configuracao,
  observacoes = excluded.observacoes,
  atualizado_em = now();
