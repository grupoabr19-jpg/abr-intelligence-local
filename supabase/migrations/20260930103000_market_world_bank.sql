create table if not exists public.raw_world_bank_indicator (
  id bigserial primary key,
  country_code text not null,
  country_name text,
  indicator_code text not null,
  indicator_name text,
  ano integer not null,
  valor numeric,
  unit text,
  obs_status text,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create table if not exists public.fact_world_bank_macro (
  id bigserial primary key,
  periodo_inicio date not null,
  country_code text not null,
  country_name text,
  indicator_code text not null,
  indicator_name text,
  valor numeric,
  unidade text,
  coletado_em timestamptz not null default now()
);

create unique index if not exists uq_raw_world_bank_indicator_grain
  on public.raw_world_bank_indicator (country_code, indicator_code, ano);

create unique index if not exists uq_fact_world_bank_macro_grain
  on public.fact_world_bank_macro (periodo_inicio, country_code, indicator_code);

create index if not exists fact_world_bank_macro_period_idx
  on public.fact_world_bank_macro (periodo_inicio desc, country_code, indicator_code);

alter table public.raw_world_bank_indicator enable row level security;
alter table public.fact_world_bank_macro enable row level security;

drop policy if exists raw_world_bank_indicator_read_public on public.raw_world_bank_indicator;
create policy raw_world_bank_indicator_read_public on public.raw_world_bank_indicator for select to anon, authenticated using (true);

drop policy if exists fact_world_bank_macro_read_public on public.fact_world_bank_macro;
create policy fact_world_bank_macro_read_public on public.fact_world_bank_macro for select to anon, authenticated using (true);

grant select on public.raw_world_bank_indicator to anon, authenticated;
grant select on public.fact_world_bank_macro to anon, authenticated;

insert into public.mercado_fontes(source_key, nome, tipo, categoria, url_base, url_documentacao, frequencia, configuracao, observacoes)
values
  (
    'world_bank_wdi',
    'World Bank WDI',
    'api',
    'macro',
    'https://api.worldbank.org/v2',
    'https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures',
    'anual',
    '{"env_base_url": "WORLD_BANK_API_BASE_URL", "env_countries": "WORLD_BANK_COUNTRIES", "env_indicators": "WORLD_BANK_INDICATORS"}'::jsonb,
    'World Bank Indicators API v2. Serie macro anual para contexto de mercado.'
  )
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
