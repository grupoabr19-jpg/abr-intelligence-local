create table if not exists public.raw_aco_brasil (
  id bigserial primary key,
  indicador_key text not null,
  indicador_nome text not null,
  periodo_inicio date not null,
  periodo_label text,
  unidade text,
  valor numeric,
  dimensoes jsonb not null default '{}'::jsonb,
  payload_original jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create table if not exists public.raw_inda (
  id bigserial primary key,
  periodo_inicio date not null,
  periodo_label text,
  indicador_key text not null,
  indicador_nome text not null,
  variacao_mes_pct numeric,
  variacao_ano_pct numeric,
  payload_original jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now(),
  unique (periodo_inicio, indicador_key)
);

create index if not exists raw_aco_brasil_period_idx
  on public.raw_aco_brasil (periodo_inicio desc, indicador_key);

create unique index if not exists uq_raw_aco_brasil_grain
  on public.raw_aco_brasil (indicador_key, periodo_inicio, md5(dimensoes::text));

create index if not exists raw_inda_period_idx
  on public.raw_inda (periodo_inicio desc, indicador_key);

alter table public.raw_aco_brasil enable row level security;
alter table public.raw_inda enable row level security;

drop policy if exists raw_aco_brasil_read_public on public.raw_aco_brasil;
create policy raw_aco_brasil_read_public
  on public.raw_aco_brasil
  for select
  to anon, authenticated
  using (true);

drop policy if exists raw_inda_read_public on public.raw_inda;
create policy raw_inda_read_public
  on public.raw_inda
  for select
  to anon, authenticated
  using (true);

grant select on public.raw_aco_brasil to anon, authenticated;
grant select on public.raw_inda to anon, authenticated;
