create extension if not exists pgcrypto;

create table if not exists public.data_archive_catalog (
  id uuid primary key default gen_random_uuid(),
  source_system text not null,
  entity text not null,
  sync_id text,
  storage_provider text not null,
  storage_path text not null,
  storage_url text,
  format text not null,
  mime_type text,
  row_count bigint not null default 0,
  byte_size bigint not null default 0,
  sha256 text not null,
  metadata jsonb not null default '{}'::jsonb,
  archived_at timestamptz not null default now()
);

create unique index if not exists uq_data_archive_catalog_provider_path
  on public.data_archive_catalog(storage_provider, storage_path);

create index if not exists idx_data_archive_catalog_entity_sync
  on public.data_archive_catalog(entity, sync_id);

create index if not exists idx_data_archive_catalog_archived
  on public.data_archive_catalog(archived_at desc);

alter table public.data_archive_catalog enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'data_archive_catalog'
      and policyname = 'data_archive_catalog_auth_select'
  ) then
    create policy data_archive_catalog_auth_select
      on public.data_archive_catalog
      for select
      to authenticated
      using (true);
  end if;
end $$;
