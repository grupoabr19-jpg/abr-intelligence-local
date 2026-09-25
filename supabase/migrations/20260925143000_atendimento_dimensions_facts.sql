alter table public.dim_regiao_varejo
  drop constraint if exists dim_regiao_varejo_funcao_chk;

alter table public.dim_regiao_varejo
  drop constraint if exists dim_regiao_varejo_regiao_chk;

alter table public.dim_regiao_varejo
  add constraint dim_regiao_varejo_funcao_chk
  check (funcao in ('VENDEDOR EXTERNO', 'ESPECIALISTA', 'CORPORATIVO', 'CONSTRUÇÃO CIVIL', 'ATACADO'));

alter table public.dim_regiao_varejo
  add constraint dim_regiao_varejo_regiao_chk
  check (regiao_polo in ('BRAGANÇA', 'JUNDIAÍ', 'VARGINHA', 'POUSO ALEGRE', 'POÇOS DE CALDAS', 'ITAJUBÁ', 'EXTREMA', 'CAMBUÍ', 'ATACADO'));

insert into public.dim_regiao_varejo (colaborador, funcao, regiao_polo)
values
  ('WILSON BUENO', 'ATACADO', 'ATACADO'),
  ('LARISSA', 'ATACADO', 'ATACADO'),
  ('JULIO', 'ATACADO', 'ATACADO')
on conflict (colaborador, funcao) do update
set regiao_polo = excluded.regiao_polo,
    atualizado_em = now();

create table if not exists public.dim_atendimento_regiao_polo (
  regiao_polo text primary key,
  canal text not null default 'VAREJO',
  ativo boolean not null default true,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.dim_atendimento_colaborador (
  colaborador_key text primary key,
  nome text not null,
  funcao text not null,
  regiao_polo text not null references public.dim_atendimento_regiao_polo(regiao_polo),
  kommo_user_id bigint,
  origem text not null default 'cadastro_operacional',
  ativo boolean not null default true,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.dim_kommo_pipeline (
  pipeline_id bigint primary key,
  nome text not null,
  ativo boolean not null default true,
  raw_hash text,
  sync_id text,
  atualizado_em timestamptz not null default now()
);

create table if not exists public.dim_kommo_status (
  status_id bigint primary key,
  pipeline_id bigint references public.dim_kommo_pipeline(pipeline_id),
  nome text not null,
  tipo_status text not null default 'andamento'
    check (tipo_status in ('andamento', 'ganha', 'perdida', 'interno', 'lideranca')),
  ativo boolean not null default true,
  raw_hash text,
  sync_id text,
  atualizado_em timestamptz not null default now()
);

create table if not exists public.dim_atendimento_origem (
  origem_key text primary key,
  origem text not null,
  ativo boolean not null default true,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

create table if not exists public.fato_atendimento_lead (
  lead_id text primary key,
  nome_lead text,
  created_at_kommo timestamptz,
  updated_at_kommo timestamptz,
  closed_at_kommo timestamptz,
  pipeline_id bigint references public.dim_kommo_pipeline(pipeline_id),
  status_id bigint references public.dim_kommo_status(status_id),
  colaborador_key text references public.dim_atendimento_colaborador(colaborador_key),
  origem_key text references public.dim_atendimento_origem(origem_key),
  situacao text not null default 'Aberto',
  valor numeric not null default 0,
  is_aberto boolean not null default false,
  is_ganho boolean not null default false,
  is_perdido boolean not null default false,
  excluido boolean not null default false,
  motivo_exclusao text,
  raw_hash text,
  sync_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fato_atendimento_sla (
  lead_id text primary key references public.fato_atendimento_lead(lead_id) on delete cascade,
  primeiro_contato_em timestamptz,
  primeira_resposta_em timestamptz,
  espera_minutos numeric,
  sla_valido boolean not null default false,
  sla_5_min boolean not null default false,
  sla_15_min boolean not null default false,
  sem_resposta boolean not null default false,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fato_atendimento_followup (
  lead_id text primary key references public.fato_atendimento_lead(lead_id) on delete cascade,
  proxima_tarefa_em timestamptz,
  tem_followup boolean not null default false,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.atendimento_data_quality (
  id uuid primary key default gen_random_uuid(),
  checked_at timestamptz not null default now(),
  regra text not null,
  severidade text not null default 'info' check (severidade in ('info', 'warning', 'error')),
  total integer not null default 0,
  detalhes jsonb not null default '{}'::jsonb
);

create table if not exists public.atendimento_refresh_runs (
  id uuid primary key default gen_random_uuid(),
  sync_id text not null,
  status text not null default 'processando' check (status in ('processando', 'sucesso', 'erro')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  leads_processados integer not null default 0,
  colaboradores integer not null default 0,
  regioes integer not null default 0,
  pipelines integer not null default 0,
  status_kommo integer not null default 0,
  origens integer not null default 0,
  erro text
);

create index if not exists idx_fato_atendimento_lead_created
  on public.fato_atendimento_lead(created_at_kommo);
create index if not exists idx_fato_atendimento_lead_colaborador
  on public.fato_atendimento_lead(colaborador_key);
create index if not exists idx_fato_atendimento_lead_status
  on public.fato_atendimento_lead(status_id);
create index if not exists idx_fato_atendimento_lead_flags
  on public.fato_atendimento_lead(is_aberto, is_ganho, is_perdido, excluido);
create index if not exists idx_atendimento_refresh_runs_started
  on public.atendimento_refresh_runs(started_at desc);
create index if not exists idx_atendimento_data_quality_checked
  on public.atendimento_data_quality(checked_at desc);

alter table public.dim_atendimento_regiao_polo enable row level security;
alter table public.dim_atendimento_colaborador enable row level security;
alter table public.dim_kommo_pipeline enable row level security;
alter table public.dim_kommo_status enable row level security;
alter table public.dim_atendimento_origem enable row level security;
alter table public.fato_atendimento_lead enable row level security;
alter table public.fato_atendimento_sla enable row level security;
alter table public.fato_atendimento_followup enable row level security;
alter table public.atendimento_data_quality enable row level security;
alter table public.atendimento_refresh_runs enable row level security;

drop policy if exists "dim_atendimento_regiao_polo_auth_select" on public.dim_atendimento_regiao_polo;
create policy "dim_atendimento_regiao_polo_auth_select" on public.dim_atendimento_regiao_polo for select to authenticated using (true);
drop policy if exists "dim_atendimento_colaborador_auth_select" on public.dim_atendimento_colaborador;
create policy "dim_atendimento_colaborador_auth_select" on public.dim_atendimento_colaborador for select to authenticated using (true);
drop policy if exists "dim_kommo_pipeline_auth_select" on public.dim_kommo_pipeline;
create policy "dim_kommo_pipeline_auth_select" on public.dim_kommo_pipeline for select to authenticated using (true);
drop policy if exists "dim_kommo_status_auth_select" on public.dim_kommo_status;
create policy "dim_kommo_status_auth_select" on public.dim_kommo_status for select to authenticated using (true);
drop policy if exists "dim_atendimento_origem_auth_select" on public.dim_atendimento_origem;
create policy "dim_atendimento_origem_auth_select" on public.dim_atendimento_origem for select to authenticated using (true);
drop policy if exists "fato_atendimento_lead_auth_select" on public.fato_atendimento_lead;
create policy "fato_atendimento_lead_auth_select" on public.fato_atendimento_lead for select to authenticated using (true);
drop policy if exists "fato_atendimento_sla_auth_select" on public.fato_atendimento_sla;
create policy "fato_atendimento_sla_auth_select" on public.fato_atendimento_sla for select to authenticated using (true);
drop policy if exists "fato_atendimento_followup_auth_select" on public.fato_atendimento_followup;
create policy "fato_atendimento_followup_auth_select" on public.fato_atendimento_followup for select to authenticated using (true);
drop policy if exists "atendimento_data_quality_auth_select" on public.atendimento_data_quality;
create policy "atendimento_data_quality_auth_select" on public.atendimento_data_quality for select to authenticated using (true);
drop policy if exists "atendimento_refresh_runs_auth_select" on public.atendimento_refresh_runs;
create policy "atendimento_refresh_runs_auth_select" on public.atendimento_refresh_runs for select to authenticated using (true);
