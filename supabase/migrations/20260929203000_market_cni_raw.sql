create table if not exists public.raw_cni_industria (
  id bigserial primary key,
  indicador_key text not null,
  indicador_nome text not null,
  periodo_inicio date not null,
  periodo_label text,
  unidade text,
  valor numeric,
  recorte text,
  dimensoes jsonb not null default '{}'::jsonb,
  payload_original jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create table if not exists public.raw_cni_construcao (
  id bigserial primary key,
  indicador_key text not null,
  indicador_nome text not null,
  periodo_inicio date not null,
  periodo_label text,
  unidade text,
  valor numeric,
  recorte text,
  dimensoes jsonb not null default '{}'::jsonb,
  payload_original jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create unique index if not exists uq_raw_cni_industria_grain
  on public.raw_cni_industria (indicador_key, periodo_inicio, coalesce(recorte, ''), md5(dimensoes::text));

create unique index if not exists uq_raw_cni_construcao_grain
  on public.raw_cni_construcao (indicador_key, periodo_inicio, coalesce(recorte, ''), md5(dimensoes::text));

create index if not exists raw_cni_industria_period_idx
  on public.raw_cni_industria (periodo_inicio desc, indicador_key);

create index if not exists raw_cni_construcao_period_idx
  on public.raw_cni_construcao (periodo_inicio desc, indicador_key);

alter table public.raw_cni_industria enable row level security;
alter table public.raw_cni_construcao enable row level security;

drop policy if exists raw_cni_industria_read_public on public.raw_cni_industria;
create policy raw_cni_industria_read_public
  on public.raw_cni_industria
  for select
  to anon, authenticated
  using (true);

drop policy if exists raw_cni_construcao_read_public on public.raw_cni_construcao;
create policy raw_cni_construcao_read_public
  on public.raw_cni_construcao
  for select
  to anon, authenticated
  using (true);

grant select on public.raw_cni_industria to anon, authenticated;
grant select on public.raw_cni_construcao to anon, authenticated;
