create extension if not exists pgcrypto;

create table if not exists public.drive_spreadsheet_ingestions (
  id uuid primary key default gen_random_uuid(),
  drive_file_id text not null,
  drive_file_name text not null,
  drive_mime_type text,
  drive_modified_time timestamptz,
  drive_parent_id text,
  file_sha256 text,
  local_path text,
  source_type text not null default 'google_drive_archive',
  detected_type text not null default 'GERAL',
  status text not null default 'processando'
    check (status in ('processando', 'sucesso', 'erro', 'ignorado')),
  sync_id text not null,
  worksheets jsonb not null default '[]'::jsonb,
  rows_read integer not null default 0,
  rows_inserted integer not null default 0,
  error_message text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  metadata jsonb not null default '{}'::jsonb
);

create unique index if not exists uq_drive_spreadsheet_ingestions_file_modified
  on public.drive_spreadsheet_ingestions(drive_file_id, drive_modified_time);

create index if not exists idx_drive_spreadsheet_ingestions_finished
  on public.drive_spreadsheet_ingestions(finished_at desc);

create index if not exists idx_drive_spreadsheet_ingestions_status
  on public.drive_spreadsheet_ingestions(status);

alter table public.drive_spreadsheet_ingestions enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'drive_spreadsheet_ingestions'
      and policyname = 'drive_spreadsheet_ingestions_auth_select'
  ) then
    create policy drive_spreadsheet_ingestions_auth_select
      on public.drive_spreadsheet_ingestions
      for select
      to authenticated
      using (true);
  end if;
end $$;
