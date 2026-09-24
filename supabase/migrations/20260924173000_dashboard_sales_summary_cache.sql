create table if not exists public.dashboard_sales_summary_cache (
  cache_key text primary key,
  date_from date,
  date_to date,
  payload jsonb not null,
  refreshed_at timestamptz not null default now()
);

create index if not exists dashboard_sales_summary_cache_period_idx
  on public.dashboard_sales_summary_cache (date_from, date_to);
