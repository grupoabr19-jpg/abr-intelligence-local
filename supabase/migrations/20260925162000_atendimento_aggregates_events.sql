alter table public.atendimento_ingestion_runs
  add column if not exists events_status text,
  add column if not exists events_erro text;

create table if not exists public.atendimento_agregado_diario (
  data_referencia date primary key,
  leads integer not null default 0,
  abertos integer not null default 0,
  ganhos integer not null default 0,
  perdidos integer not null default 0,
  pipeline_valor numeric not null default 0,
  sla_validos integer not null default 0,
  sla_5 integer not null default 0,
  sla_15 integer not null default 0,
  sem_resposta integer not null default 0,
  abertos_com_followup integer not null default 0,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.atendimento_agregado_colaborador (
  colaborador_key text not null references public.dim_atendimento_colaborador(colaborador_key),
  data_referencia date not null,
  leads integer not null default 0,
  abertos integer not null default 0,
  ganhos integer not null default 0,
  perdidos integer not null default 0,
  pipeline_valor numeric not null default 0,
  sla_validos integer not null default 0,
  sla_5 integer not null default 0,
  sla_15 integer not null default 0,
  sem_resposta integer not null default 0,
  abertos_com_followup integer not null default 0,
  refreshed_at timestamptz not null default now(),
  primary key (colaborador_key, data_referencia)
);

create table if not exists public.atendimento_agregado_regiao (
  regiao_polo text not null references public.dim_atendimento_regiao_polo(regiao_polo),
  data_referencia date not null,
  leads integer not null default 0,
  abertos integer not null default 0,
  ganhos integer not null default 0,
  perdidos integer not null default 0,
  pipeline_valor numeric not null default 0,
  sla_validos integer not null default 0,
  sla_5 integer not null default 0,
  sla_15 integer not null default 0,
  sem_resposta integer not null default 0,
  abertos_com_followup integer not null default 0,
  refreshed_at timestamptz not null default now(),
  primary key (regiao_polo, data_referencia)
);

create table if not exists public.atendimento_evento_resposta (
  lead_id text not null references public.fato_atendimento_lead(lead_id) on delete cascade,
  evento_id text not null,
  event_type text,
  created_by bigint,
  created_at_kommo timestamptz,
  raw_hash text,
  sync_id text,
  refreshed_at timestamptz not null default now(),
  primary key (lead_id, evento_id)
);

alter table public.atendimento_refresh_runs
  add column if not exists agregados_diarios integer not null default 0,
  add column if not exists agregados_colaboradores integer not null default 0,
  add column if not exists agregados_regioes integer not null default 0,
  add column if not exists eventos_resposta integer not null default 0;

create index if not exists idx_atendimento_agregado_colaborador_data
  on public.atendimento_agregado_colaborador(data_referencia);
create index if not exists idx_atendimento_agregado_regiao_data
  on public.atendimento_agregado_regiao(data_referencia);
create index if not exists idx_atendimento_evento_resposta_data
  on public.atendimento_evento_resposta(created_at_kommo);

alter table public.atendimento_agregado_diario enable row level security;
alter table public.atendimento_agregado_colaborador enable row level security;
alter table public.atendimento_agregado_regiao enable row level security;
alter table public.atendimento_evento_resposta enable row level security;

drop policy if exists "atendimento_agregado_diario_auth_select" on public.atendimento_agregado_diario;
create policy "atendimento_agregado_diario_auth_select" on public.atendimento_agregado_diario
  for select to authenticated using (true);

drop policy if exists "atendimento_agregado_colaborador_auth_select" on public.atendimento_agregado_colaborador;
create policy "atendimento_agregado_colaborador_auth_select" on public.atendimento_agregado_colaborador
  for select to authenticated using (true);

drop policy if exists "atendimento_agregado_regiao_auth_select" on public.atendimento_agregado_regiao;
create policy "atendimento_agregado_regiao_auth_select" on public.atendimento_agregado_regiao
  for select to authenticated using (true);

drop policy if exists "atendimento_evento_resposta_auth_select" on public.atendimento_evento_resposta;
create policy "atendimento_evento_resposta_auth_select" on public.atendimento_evento_resposta
  for select to authenticated using (true);
