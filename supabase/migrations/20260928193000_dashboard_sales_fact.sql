create table if not exists public.dashboard_sales_fact (
  staging_id uuid primary key,
  source_id text,
  hash_registro text,
  sync_id text,
  imported_at timestamptz,
  sale_date date,
  valor_total numeric not null default 0,
  receita_liquida numeric not null default 0,
  lucro_bruto numeric not null default 0,
  margem_contribuicao numeric not null default 0,
  peso_total numeric not null default 0,
  cliente_codigo text,
  cliente text not null default 'Sem cliente',
  item text,
  produto text not null default 'Sem item',
  familia text not null default 'Sem familia',
  segmento text not null default 'Sem segmento',
  cidade text not null default 'Sem cidade',
  estado text not null default 'Sem UF',
  vendedor text not null default 'Sem vendedor',
  tipo text not null default 'Sem tipo',
  nota_fiscal text,
  valor_perdido numeric not null default 0,
  motivo_perda text not null default 'Sem motivo',
  refreshed_at timestamptz not null default now()
);

create index if not exists dashboard_sales_fact_sale_date_idx
  on public.dashboard_sales_fact (sale_date);

create index if not exists dashboard_sales_fact_dimensions_idx
  on public.dashboard_sales_fact (familia, segmento, vendedor, cliente);

create index if not exists dashboard_sales_fact_sync_idx
  on public.dashboard_sales_fact (sync_id, imported_at);

alter table public.dashboard_sales_fact enable row level security;

drop policy if exists "dashboard_sales_fact_auth_select" on public.dashboard_sales_fact;
create policy "dashboard_sales_fact_auth_select"
  on public.dashboard_sales_fact
  for select
  to authenticated
  using (true);
