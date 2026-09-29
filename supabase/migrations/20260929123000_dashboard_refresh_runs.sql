create table if not exists public.dashboard_refresh_runs (
  job_id uuid primary key,
  mode text not null,
  status text not null,
  date_from date not null,
  date_to date not null,
  message text not null default '',
  created_at timestamptz not null,
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.dashboard_refresh_steps (
  job_id uuid not null references public.dashboard_refresh_runs(job_id) on delete cascade,
  step_index int not null,
  step_key text not null,
  label text not null,
  status text not null,
  started_at timestamptz,
  finished_at timestamptz,
  return_code int,
  stdout_tail text not null default '',
  stderr_tail text not null default '',
  result jsonb,
  error text,
  updated_at timestamptz not null default now(),
  primary key (job_id, step_index)
);

create index if not exists dashboard_refresh_runs_created_idx
  on public.dashboard_refresh_runs (created_at desc);

create index if not exists dashboard_refresh_runs_status_idx
  on public.dashboard_refresh_runs (status, created_at desc);

alter table public.dashboard_refresh_runs enable row level security;
alter table public.dashboard_refresh_steps enable row level security;

drop policy if exists "dashboard_refresh_runs_auth_select" on public.dashboard_refresh_runs;
create policy "dashboard_refresh_runs_auth_select"
  on public.dashboard_refresh_runs
  for select
  to authenticated
  using (true);

drop policy if exists "dashboard_refresh_steps_auth_select" on public.dashboard_refresh_steps;
create policy "dashboard_refresh_steps_auth_select"
  on public.dashboard_refresh_steps
  for select
  to authenticated
  using (true);
