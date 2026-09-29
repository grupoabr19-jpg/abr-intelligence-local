create table if not exists public.raw_bcb_ptax (
  id bigserial primary key,
  data_cotacao date not null,
  data_hora_cotacao timestamptz not null,
  tipo_boletim text,
  cotacao_compra numeric,
  cotacao_venda numeric,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create table if not exists public.raw_ibge_sidra (
  id bigserial primary key,
  source_key text not null,
  table_id text not null,
  variable_id text,
  period_code text,
  period_label text,
  geography_code text,
  geography_name text,
  classification_code text,
  classification_name text,
  category_code text,
  category_name text,
  value numeric,
  value_text text,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create index if not exists raw_bcb_ptax_data_idx
  on public.raw_bcb_ptax (data_cotacao desc);

create unique index if not exists uq_raw_bcb_ptax_grain
  on public.raw_bcb_ptax (data_hora_cotacao, coalesce(tipo_boletim, ''));

create index if not exists raw_ibge_sidra_source_period_idx
  on public.raw_ibge_sidra (source_key, period_code desc);

create unique index if not exists uq_raw_ibge_sidra_grain
  on public.raw_ibge_sidra (
    source_key,
    table_id,
    coalesce(variable_id, ''),
    coalesce(period_code, ''),
    coalesce(geography_code, ''),
    coalesce(classification_code, ''),
    coalesce(category_code, '')
  );

alter table public.raw_bcb_ptax enable row level security;
alter table public.raw_ibge_sidra enable row level security;

drop policy if exists raw_bcb_ptax_read_public on public.raw_bcb_ptax;
create policy raw_bcb_ptax_read_public
  on public.raw_bcb_ptax
  for select
  to anon, authenticated
  using (true);

drop policy if exists raw_ibge_sidra_read_public on public.raw_ibge_sidra;
create policy raw_ibge_sidra_read_public
  on public.raw_ibge_sidra
  for select
  to anon, authenticated
  using (true);

grant select on public.raw_bcb_ptax to anon, authenticated;
grant select on public.raw_ibge_sidra to anon, authenticated;

insert into public.mercado_fontes(source_key, nome, tipo, categoria, url_base, url_documentacao, frequencia, configuracao, observacoes)
values
  ('ibge_construcao_sidra', 'IBGE construcao SIDRA', 'api', 'construcao', 'https://apisidra.ibge.gov.br/values', 'https://apisidra.ibge.gov.br/DescritoresTabela/t', 'mensal', '{"env_values_url": "IBGE_SIDRA_VALUES_BASE_URL", "env_descriptor_url": "IBGE_SIDRA_DESCRIPTOR_BASE_URL", "env_table_id": "IBGE_CONSTRUCTION_TABLE_ID", "env_default_path": "IBGE_CONSTRUCTION_DEFAULT_PATH"}'::jsonb, 'API publica SIDRA, sem token.')
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
