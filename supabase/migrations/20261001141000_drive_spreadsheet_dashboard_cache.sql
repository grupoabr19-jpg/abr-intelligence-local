create table if not exists public.dashboard_drive_spreadsheet_cache (
  cache_key text primary key,
  detected_type text not null,
  drive_file_id text not null,
  drive_file_name text not null,
  drive_modified_time timestamptz,
  row_count integer not null default 0,
  payload jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now()
);

create index if not exists idx_dashboard_drive_spreadsheet_cache_type_modified
  on public.dashboard_drive_spreadsheet_cache(detected_type, drive_modified_time desc);

alter table public.dashboard_drive_spreadsheet_cache enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'dashboard_drive_spreadsheet_cache'
      and policyname = 'dashboard_drive_spreadsheet_cache_auth_select'
  ) then
    create policy dashboard_drive_spreadsheet_cache_auth_select
      on public.dashboard_drive_spreadsheet_cache
      for select
      to authenticated
      using (true);
  end if;
end $$;
