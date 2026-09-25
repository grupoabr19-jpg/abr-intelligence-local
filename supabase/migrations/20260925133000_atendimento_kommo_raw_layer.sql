create table if not exists public.atendimento_ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  source_system text not null default 'KOMMO_API',
  entidade text not null default 'atendimento_kommo',
  sync_id text not null unique,
  status text not null default 'processando'
    check (status in ('processando', 'sucesso', 'parcial', 'erro')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  date_from date,
  date_to date,
  page_limit integer,
  max_pages integer,
  users_lidos integer not null default 0,
  pipelines_lidos integer not null default 0,
  statuses_lidos integer not null default 0,
  leads_lidos integer not null default 0,
  tasks_lidas integer not null default 0,
  events_lidos integer not null default 0,
  staging_inseridos integer not null default 0,
  staging_ignorados integer not null default 0,
  raw_inseridos integer not null default 0,
  raw_ignorados integer not null default 0,
  erro text,
  metadata jsonb not null default '{}'::jsonb
);

comment on table public.atendimento_ingestion_runs is
  'Execucoes de ingestao do modulo Atendimento. Registra cargas Kommo e contagens por entidade.';

create table if not exists public.raw_kommo_users (
  id uuid primary key default gen_random_uuid(),
  kommo_user_id bigint not null,
  name text,
  email text,
  raw_payload jsonb not null,
  raw_hash text not null,
  sync_id text not null,
  fetched_at timestamptz not null default now(),
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_raw_kommo_users_version unique (kommo_user_id, raw_hash)
);

create table if not exists public.raw_kommo_pipelines (
  id uuid primary key default gen_random_uuid(),
  kommo_pipeline_id bigint not null,
  name text,
  raw_payload jsonb not null,
  raw_hash text not null,
  sync_id text not null,
  fetched_at timestamptz not null default now(),
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_raw_kommo_pipelines_version unique (kommo_pipeline_id, raw_hash)
);

create table if not exists public.raw_kommo_statuses (
  id uuid primary key default gen_random_uuid(),
  kommo_status_id bigint not null,
  kommo_pipeline_id bigint,
  name text,
  raw_payload jsonb not null,
  raw_hash text not null,
  sync_id text not null,
  fetched_at timestamptz not null default now(),
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_raw_kommo_statuses_version unique (kommo_status_id, raw_hash)
);

create table if not exists public.raw_kommo_leads (
  id uuid primary key default gen_random_uuid(),
  kommo_lead_id bigint not null,
  kommo_pipeline_id bigint,
  kommo_status_id bigint,
  responsible_user_id bigint,
  name text,
  price numeric,
  created_at_kommo timestamptz,
  updated_at_kommo timestamptz,
  closed_at_kommo timestamptz,
  raw_payload jsonb not null,
  raw_hash text not null,
  sync_id text not null,
  fetched_at timestamptz not null default now(),
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_raw_kommo_leads_version unique (kommo_lead_id, raw_hash)
);

create table if not exists public.raw_kommo_tasks (
  id uuid primary key default gen_random_uuid(),
  kommo_task_id bigint not null,
  entity_type text,
  entity_id bigint,
  responsible_user_id bigint,
  is_completed boolean,
  complete_till_kommo timestamptz,
  raw_payload jsonb not null,
  raw_hash text not null,
  sync_id text not null,
  fetched_at timestamptz not null default now(),
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_raw_kommo_tasks_version unique (kommo_task_id, raw_hash)
);

create table if not exists public.raw_kommo_events (
  id uuid primary key default gen_random_uuid(),
  kommo_event_id text not null,
  entity_type text,
  entity_id bigint,
  event_type text,
  created_by bigint,
  created_at_kommo timestamptz,
  raw_payload jsonb not null,
  raw_hash text not null,
  sync_id text not null,
  fetched_at timestamptz not null default now(),
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_raw_kommo_events_version unique (kommo_event_id, raw_hash)
);

create index if not exists idx_atendimento_ingestion_runs_started
  on public.atendimento_ingestion_runs (started_at desc);
create index if not exists idx_raw_kommo_users_current
  on public.raw_kommo_users (kommo_user_id) where ativo = true;
create index if not exists idx_raw_kommo_pipelines_current
  on public.raw_kommo_pipelines (kommo_pipeline_id) where ativo = true;
create index if not exists idx_raw_kommo_statuses_current
  on public.raw_kommo_statuses (kommo_status_id, kommo_pipeline_id) where ativo = true;
create index if not exists idx_raw_kommo_leads_current
  on public.raw_kommo_leads (kommo_lead_id) where ativo = true;
create index if not exists idx_raw_kommo_leads_created
  on public.raw_kommo_leads (created_at_kommo);
create index if not exists idx_raw_kommo_tasks_current
  on public.raw_kommo_tasks (kommo_task_id) where ativo = true;
create index if not exists idx_raw_kommo_tasks_entity
  on public.raw_kommo_tasks (entity_type, entity_id);
create index if not exists idx_raw_kommo_events_current
  on public.raw_kommo_events (kommo_event_id) where ativo = true;
create index if not exists idx_raw_kommo_events_entity
  on public.raw_kommo_events (entity_type, entity_id);

alter table public.atendimento_ingestion_runs enable row level security;
alter table public.raw_kommo_users enable row level security;
alter table public.raw_kommo_pipelines enable row level security;
alter table public.raw_kommo_statuses enable row level security;
alter table public.raw_kommo_leads enable row level security;
alter table public.raw_kommo_tasks enable row level security;
alter table public.raw_kommo_events enable row level security;

drop policy if exists "atendimento_ingestion_runs_auth_select" on public.atendimento_ingestion_runs;
create policy "atendimento_ingestion_runs_auth_select" on public.atendimento_ingestion_runs
  for select to authenticated
  using (true);

drop policy if exists "raw_kommo_users_auth_select" on public.raw_kommo_users;
create policy "raw_kommo_users_auth_select" on public.raw_kommo_users
  for select to authenticated
  using (true);

drop policy if exists "raw_kommo_pipelines_auth_select" on public.raw_kommo_pipelines;
create policy "raw_kommo_pipelines_auth_select" on public.raw_kommo_pipelines
  for select to authenticated
  using (true);

drop policy if exists "raw_kommo_statuses_auth_select" on public.raw_kommo_statuses;
create policy "raw_kommo_statuses_auth_select" on public.raw_kommo_statuses
  for select to authenticated
  using (true);

drop policy if exists "raw_kommo_leads_auth_select" on public.raw_kommo_leads;
create policy "raw_kommo_leads_auth_select" on public.raw_kommo_leads
  for select to authenticated
  using (true);

drop policy if exists "raw_kommo_tasks_auth_select" on public.raw_kommo_tasks;
create policy "raw_kommo_tasks_auth_select" on public.raw_kommo_tasks
  for select to authenticated
  using (true);

drop policy if exists "raw_kommo_events_auth_select" on public.raw_kommo_events;
create policy "raw_kommo_events_auth_select" on public.raw_kommo_events
  for select to authenticated
  using (true);
