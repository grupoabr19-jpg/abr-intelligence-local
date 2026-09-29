create table if not exists public.market_source_registry (
  source_key text primary key,
  source_name text not null,
  source_type text not null check (source_type in ('api', 'html', 'download', 'csv', 'parquet', 'microdados', 'ftp')),
  category text not null default 'mercado',
  frequency text not null default 'mensal',
  configured boolean not null default false,
  reachable boolean not null default false,
  status text not null default 'DISABLED' check (status in ('DISABLED', 'CONFIGURED', 'HEALTHY', 'STALE', 'ERROR')),
  base_url text,
  docs_url text,
  env_keys jsonb not null default '[]'::jsonb,
  last_success_at timestamptz,
  latest_reference_period text,
  last_row_count integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}'::jsonb,
  checked_at timestamptz,
  updated_at timestamptz not null default now()
);

create index if not exists market_source_registry_status_idx
  on public.market_source_registry (status, category, source_key);

alter table public.market_source_registry enable row level security;

drop policy if exists market_source_registry_read_public on public.market_source_registry;
create policy market_source_registry_read_public
  on public.market_source_registry
  for select
  to anon, authenticated
  using (true);

grant select on public.market_source_registry to anon, authenticated;
