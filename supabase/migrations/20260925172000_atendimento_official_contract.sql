create extension if not exists unaccent;

create table if not exists public.raw_kommo_contacts (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'KOMMO_API',
  source_record_id text not null,
  extracted_at timestamptz not null default now(),
  reference_date date,
  batch_id text not null,
  raw_payload_hash text not null,
  raw_payload jsonb not null,
  ativo boolean not null default true,
  unique (source, source_record_id, raw_payload_hash)
);

create table if not exists public.raw_kommo_companies (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'KOMMO_API',
  source_record_id text not null,
  extracted_at timestamptz not null default now(),
  reference_date date,
  batch_id text not null,
  raw_payload_hash text not null,
  raw_payload jsonb not null,
  ativo boolean not null default true,
  unique (source, source_record_id, raw_payload_hash)
);

create table if not exists public.raw_aster_sales (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'ASTER',
  source_record_id text not null,
  extracted_at timestamptz not null default now(),
  reference_date date,
  batch_id text not null,
  raw_payload_hash text not null,
  raw_payload jsonb not null,
  ativo boolean not null default true,
  unique (source, source_record_id, raw_payload_hash)
);

create table if not exists public.raw_aster_orders (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'ASTER',
  source_record_id text not null,
  extracted_at timestamptz not null default now(),
  reference_date date,
  batch_id text not null,
  raw_payload_hash text not null,
  raw_payload jsonb not null,
  ativo boolean not null default true,
  unique (source, source_record_id, raw_payload_hash)
);

create table if not exists public.raw_production (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'GESTAO_PRODUCAO',
  source_record_id text not null,
  extracted_at timestamptz not null default now(),
  reference_date date,
  batch_id text not null,
  raw_payload_hash text not null,
  raw_payload jsonb not null,
  ativo boolean not null default true,
  unique (source, source_record_id, raw_payload_hash)
);

create table if not exists public.raw_ranking (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'RANKING',
  source_record_id text not null,
  extracted_at timestamptz not null default now(),
  reference_date date,
  batch_id text not null,
  raw_payload_hash text not null,
  raw_payload jsonb not null,
  ativo boolean not null default true,
  unique (source, source_record_id, raw_payload_hash)
);

create table if not exists public.raw_targets (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'METAS',
  source_record_id text not null,
  extracted_at timestamptz not null default now(),
  reference_date date,
  batch_id text not null,
  raw_payload_hash text not null,
  raw_payload jsonb not null,
  ativo boolean not null default true,
  unique (source, source_record_id, raw_payload_hash)
);

create table if not exists public.dim_data (
  data date primary key,
  ano integer not null,
  mes integer not null,
  dia integer not null,
  ano_mes text not null,
  trimestre integer not null,
  semana integer not null
);

create table if not exists public.dim_polo (
  polo text primary key,
  canal text not null default 'VAREJO',
  ativo boolean not null default true
);

create table if not exists public.dim_colaborador (
  id_colaborador text primary key,
  nome_canonico text not null,
  nome_kommo text,
  nome_aster text,
  nome_ranking text,
  canal text not null,
  funcao text not null,
  polo text references public.dim_polo(polo),
  ddds text[] not null default '{}'::text[],
  ativo boolean not null default true,
  vigencia_inicio date not null default current_date,
  vigencia_fim date
);

create table if not exists public.dim_cliente (
  id_cliente text primary key,
  nome_canonico text not null,
  nome_kommo text,
  nome_aster text,
  documento text,
  telefone text,
  email text,
  ativo boolean not null default true,
  atualizado_em timestamptz not null default now()
);

create table if not exists public.dim_funil (
  id_funil text primary key,
  nome_funil text not null,
  source text not null default 'KOMMO',
  ativo boolean not null default true
);

create table if not exists public.dim_etapa (
  id_etapa text primary key,
  id_funil text references public.dim_funil(id_funil),
  nome_original text not null,
  nome_normalizado text not null,
  tipo_etapa text not null default 'andamento',
  ativo boolean not null default true
);

create table if not exists public.fact_kommo_leads (
  lead_id text primary key,
  created_at timestamptz,
  closed_at timestamptz,
  pipeline text,
  stage_original text,
  stage_normalized text,
  status text,
  responsible_id text,
  first_responder_id text,
  source text,
  segment text,
  temperature text,
  crm_value numeric not null default 0,
  first_contact_at timestamptz,
  first_human_response_at timestamptz,
  wait_minutes numeric,
  last_interaction_at timestamptz,
  next_task_at timestamptz,
  contact_id text,
  company_id text,
  id_colaborador text references public.dim_colaborador(id_colaborador),
  origem_payload_hash text,
  batch_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fact_kommo_interacoes (
  interaction_id text primary key,
  lead_id text references public.fact_kommo_leads(lead_id),
  interaction_type text,
  created_at timestamptz,
  created_by text,
  raw_payload_hash text,
  batch_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fact_kommo_tasks (
  task_id text primary key,
  lead_id text,
  responsible_id text,
  task_type text,
  complete_till timestamptz,
  is_completed boolean,
  raw_payload_hash text,
  batch_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fact_sales (
  sale_id text primary key,
  order_id text,
  customer_id text,
  seller_id text,
  sale_date date,
  weight_kg numeric not null default 0,
  revenue numeric not null default 0,
  raw_payload_hash text,
  batch_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fact_orders (
  order_id text primary key,
  customer_id text,
  seller_id text,
  order_date date,
  approval_date date,
  promised_date date,
  real_delivery_date date,
  status text,
  raw_payload_hash text,
  batch_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fact_order_items (
  order_item_id text primary key,
  order_id text references public.fact_orders(order_id),
  product_id text,
  family text,
  weight_kg numeric not null default 0,
  revenue numeric not null default 0,
  raw_payload_hash text,
  batch_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.fact_production (
  production_id text primary key,
  order_id text,
  status text,
  started_at timestamptz,
  finished_at timestamptz,
  weight_kg numeric not null default 0,
  raw_payload_hash text,
  batch_id text,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.bridge_lead_order (
  lead_id text not null,
  order_id text not null,
  customer_id text,
  match_method text not null,
  confidence_level text not null check (confidence_level in ('A', 'B', 'C', 'D')),
  matched_at timestamptz not null default now(),
  primary key (lead_id, order_id, match_method)
);

create table if not exists public.fact_occurrences (
  occurrence_id text primary key,
  type text not null,
  source text not null,
  lead_id text,
  order_id text,
  customer_id text,
  responsible_id text,
  opened_at timestamptz not null,
  closed_at timestamptz,
  status text not null default 'aberta',
  severity text not null default 'media',
  details jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now()
);

create table if not exists public.data_quality_alerts (
  id uuid primary key default gen_random_uuid(),
  batch_name text not null,
  rule text not null,
  severity text not null default 'warning',
  total integer not null default 0,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.colaboradores_nao_mapeados (
  nome_origem text primary key,
  source text not null,
  total_registros integer not null default 0,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

create index if not exists idx_fact_kommo_leads_created on public.fact_kommo_leads(created_at);
create index if not exists idx_fact_kommo_leads_status on public.fact_kommo_leads(status);
create index if not exists idx_fact_sales_date on public.fact_sales(sale_date);
create index if not exists idx_fact_orders_date on public.fact_orders(order_date);
create index if not exists idx_bridge_lead_order_confidence on public.bridge_lead_order(confidence_level);
create index if not exists idx_fact_occurrences_status on public.fact_occurrences(status, type);

insert into public.dim_polo(polo, canal)
values
  ('BRAGANÇA', 'VAREJO'),
  ('JUNDIAÍ', 'VAREJO'),
  ('VARGINHA', 'VAREJO'),
  ('POUSO ALEGRE', 'VAREJO'),
  ('POÇOS DE CALDAS', 'VAREJO'),
  ('ITAJUBÁ', 'VAREJO'),
  ('EXTREMA', 'VAREJO'),
  ('CAMBUÍ', 'VAREJO'),
  ('ATACADO', 'ATACADO')
on conflict (polo) do update set canal = excluded.canal, ativo = true;

insert into public.dim_colaborador(id_colaborador, nome_canonico, nome_kommo, nome_aster, nome_ranking, canal, funcao, polo, ddds)
select
  regexp_replace(upper(unaccent(colaborador)), '[^A-Z0-9]+', '', 'g'),
  colaborador,
  colaborador,
  colaborador,
  colaborador,
  case when regiao_polo = 'ATACADO' or funcao = 'ATACADO' then 'ATACADO' else 'VAREJO' end,
  funcao,
  regiao_polo,
  case
    when colaborador in ('LARISSA', 'LARISSA TERRA') then array['11','12','13']
    when colaborador in ('JULIO', 'JULIO MELO') then array['15','19']
    when colaborador in ('WILSON BUENO', 'WILSON NETO') then array['14','16','17','18']
    else '{}'::text[]
  end
from public.dim_regiao_varejo
on conflict (id_colaborador) do update
set nome_canonico = excluded.nome_canonico,
    nome_kommo = excluded.nome_kommo,
    nome_aster = excluded.nome_aster,
    nome_ranking = excluded.nome_ranking,
    canal = excluded.canal,
    funcao = excluded.funcao,
    polo = excluded.polo,
    ddds = excluded.ddds,
    ativo = true;

insert into public.dim_colaborador(id_colaborador, nome_canonico, nome_kommo, nome_aster, nome_ranking, canal, funcao, polo, ddds)
values
  ('LARISSATERRA', 'LARISSA TERRA', 'LARISSA', 'LARISSA TERRA', 'LARISSA TERRA', 'ATACADO', 'ATACADO', 'ATACADO', array['11','12','13']),
  ('JULIOMELO', 'JULIO MELO', 'JULIO', 'JULIO MELO', 'JULIO MELO', 'ATACADO', 'ATACADO', 'ATACADO', array['15','19']),
  ('WILSONNETO', 'WILSON NETO', 'WILSON BUENO', 'WILSON NETO', 'WILSON NETO', 'ATACADO', 'ATACADO', 'ATACADO', array['14','16','17','18'])
on conflict (id_colaborador) do update
set ddds = excluded.ddds,
    canal = excluded.canal,
    funcao = excluded.funcao,
    polo = excluded.polo,
    ativo = true;

insert into public.dim_data(data, ano, mes, dia, ano_mes, trimestre, semana)
select
  d::date,
  extract(year from d)::int,
  extract(month from d)::int,
  extract(day from d)::int,
  to_char(d, 'YYYY-MM'),
  extract(quarter from d)::int,
  extract(week from d)::int
from generate_series(date '2024-01-01', date '2030-12-31', interval '1 day') as d
on conflict (data) do nothing;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'raw_kommo_contacts','raw_kommo_companies','raw_aster_sales','raw_aster_orders',
    'raw_production','raw_ranking','raw_targets','dim_data','dim_polo','dim_colaborador',
    'dim_cliente','dim_funil','dim_etapa','fact_kommo_leads','fact_kommo_interacoes',
    'fact_kommo_tasks','fact_sales','fact_orders','fact_order_items','fact_production',
    'bridge_lead_order','fact_occurrences','data_quality_alerts','colaboradores_nao_mapeados'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('drop policy if exists "%s_auth_select" on public.%I', table_name, table_name);
    execute format('create policy "%s_auth_select" on public.%I for select to authenticated using (true)', table_name, table_name);
  end loop;
end $$;
