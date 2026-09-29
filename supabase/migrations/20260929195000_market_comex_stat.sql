create table if not exists public.dim_ncm_abr (
  ncm text primary key,
  descricao text not null,
  familia_abr text not null check (familia_abr in ('CHAPA FQ', 'CHAPA FF', 'GALVANIZADA', 'CHAPA GROSSA', 'TUBOS', 'PERFIS', 'OUTRAS')),
  subfamilia_abr text,
  ativo boolean not null default true,
  vigencia_inicio date,
  vigencia_fim date,
  validado_por text,
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.raw_comex_import (
  id bigserial primary key,
  co_ano integer not null,
  co_mes integer not null,
  co_ncm text not null,
  co_unid text,
  co_pais text,
  sg_uf_ncm text,
  co_via text,
  co_urf text,
  qt_estat numeric,
  kg_liquido numeric,
  vl_fob numeric,
  vl_frete numeric,
  vl_seguro numeric,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now(),
  unique (co_ano, co_mes, co_ncm, co_pais, sg_uf_ncm, co_via, co_urf)
);

create table if not exists public.fact_steel_import_monthly (
  id bigserial primary key,
  periodo_inicio date not null,
  ncm text not null references public.dim_ncm_abr(ncm),
  familia_abr text not null,
  subfamilia_abr text,
  sg_uf_ncm text,
  co_pais text,
  toneladas numeric not null default 0,
  vl_fob_usd numeric not null default 0,
  vl_frete_usd numeric not null default 0,
  vl_seguro_usd numeric not null default 0,
  fob_usd_t numeric,
  cif_proxy_usd_t numeric,
  coletado_em timestamptz not null default now()
);

create index if not exists raw_comex_import_month_ncm_idx
  on public.raw_comex_import (co_ano, co_mes, co_ncm);

create index if not exists fact_steel_import_monthly_period_family_idx
  on public.fact_steel_import_monthly (periodo_inicio desc, familia_abr);

create unique index if not exists uq_fact_steel_import_monthly_grain
  on public.fact_steel_import_monthly (
    periodo_inicio,
    ncm,
    coalesce(sg_uf_ncm, ''),
    coalesce(co_pais, '')
  );

alter table public.dim_ncm_abr enable row level security;
alter table public.raw_comex_import enable row level security;
alter table public.fact_steel_import_monthly enable row level security;

drop policy if exists dim_ncm_abr_read_public on public.dim_ncm_abr;
create policy dim_ncm_abr_read_public
  on public.dim_ncm_abr
  for select
  to anon, authenticated
  using (true);

drop policy if exists raw_comex_import_read_public on public.raw_comex_import;
create policy raw_comex_import_read_public
  on public.raw_comex_import
  for select
  to anon, authenticated
  using (true);

drop policy if exists fact_steel_import_monthly_read_public on public.fact_steel_import_monthly;
create policy fact_steel_import_monthly_read_public
  on public.fact_steel_import_monthly
  for select
  to anon, authenticated
  using (true);

grant select on public.dim_ncm_abr to anon, authenticated;
grant select on public.raw_comex_import to anon, authenticated;
grant select on public.fact_steel_import_monthly to anon, authenticated;

insert into public.mercado_fontes(source_key, nome, tipo, categoria, url_base, frequencia, configuracao, observacoes)
values
  ('comex_stat_ncm', 'Comex Stat NCM', 'csv', 'comercio_exterior', 'https://balanca.mdic.gov.br/balanca/bd/comexstat-bd/ncm', 'mensal', '{"env_csv_base_url": "COMEX_STAT_CSV_BASE_URL", "env_api_token": "COMEX_STAT_API_TOKEN"}'::jsonb, 'CSV publico anual cumulativo de importacoes por NCM. Exige dim_ncm_abr aprovada.')
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
