create table if not exists public.raw_aneel (
  id bigserial primary key,
  periodo_inicio date not null,
  data_conexao date,
  municipio text,
  uf text,
  classe text,
  fonte text,
  potencia_kw numeric not null default 0,
  novas_instalacoes integer not null default 0,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create table if not exists public.fact_solar_monthly (
  id bigserial primary key,
  periodo_inicio date not null,
  municipio text,
  uf text,
  classe text,
  fonte text,
  new_mw numeric not null default 0,
  cumulative_mw numeric not null default 0,
  novas_instalacoes integer not null default 0,
  coletado_em timestamptz not null default now()
);

create unique index if not exists uq_raw_aneel_grain
  on public.raw_aneel (
    periodo_inicio,
    coalesce(municipio, ''),
    coalesce(uf, ''),
    coalesce(classe, ''),
    coalesce(fonte, '')
  );

create unique index if not exists uq_fact_solar_monthly_grain
  on public.fact_solar_monthly (
    periodo_inicio,
    coalesce(municipio, ''),
    coalesce(uf, ''),
    coalesce(classe, ''),
    coalesce(fonte, '')
  );

create index if not exists raw_aneel_period_uf_idx
  on public.raw_aneel (periodo_inicio desc, uf, municipio);

create index if not exists fact_solar_monthly_period_uf_idx
  on public.fact_solar_monthly (periodo_inicio desc, uf, municipio);

alter table public.raw_aneel enable row level security;
alter table public.fact_solar_monthly enable row level security;

drop policy if exists raw_aneel_read_public on public.raw_aneel;
create policy raw_aneel_read_public on public.raw_aneel for select to anon, authenticated using (true);

drop policy if exists fact_solar_monthly_read_public on public.fact_solar_monthly;
create policy fact_solar_monthly_read_public on public.fact_solar_monthly for select to anon, authenticated using (true);

grant select on public.raw_aneel to anon, authenticated;
grant select on public.fact_solar_monthly to anon, authenticated;

insert into public.mercado_fontes(source_key, nome, tipo, categoria, url_base, frequencia, configuracao, observacoes)
values
  (
    'aneel_dados_abertos',
    'ANEEL geracao distribuida fotovoltaica',
    'parquet',
    'energia',
    'https://dadosabertos.aneel.gov.br',
    'mensal',
    '{"env_base_url": "ANEEL_API_BASE_URL", "dataset": "relacao-de-empreendimentos-de-geracao-distribuida"}'::jsonb,
    'Coletor descobre o recurso Parquet via CKAN e grava agregados mensais de geracao fotovoltaica em MW.'
  )
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
