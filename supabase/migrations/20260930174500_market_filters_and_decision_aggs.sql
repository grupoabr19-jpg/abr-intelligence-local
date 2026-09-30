create table if not exists public.market_tab_filter_defaults (
  tab_key text primary key,
  label text not null,
  default_months integer,
  default_days integer,
  date_from date,
  date_to date,
  filters jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.agg_market_price_pressure (
  periodo_inicio date not null,
  family text not null,
  fx_signal integer,
  fob_signal integer,
  import_signal integer,
  inda_signal integer,
  demand_signal integer,
  score integer,
  classification text not null,
  available_components_count integer not null default 0,
  status text not null default 'INSUFFICIENT_DATA',
  components jsonb not null default '{}'::jsonb,
  source_periods jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now(),
  primary key (periodo_inicio, family)
);

create table if not exists public.agg_market_demand_family (
  periodo_inicio date not null,
  family text not null,
  score integer,
  classification text not null,
  available_components_count integer not null default 0,
  status text not null default 'INSUFFICIENT_DATA',
  drivers jsonb not null default '[]'::jsonb,
  source_periods jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now(),
  primary key (periodo_inicio, family)
);

create table if not exists public.agg_market_regional (
  periodo_inicio date not null,
  polo text not null,
  steel_potential_proxy_t numeric,
  abr_sales_12m_t numeric,
  penetration_proxy numeric,
  white_space_proxy_t numeric,
  regional_momentum integer,
  classification text not null default 'INSUFFICIENT_DATA',
  components jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now(),
  primary key (periodo_inicio, polo)
);

create table if not exists public.agg_market_competition (
  snapshot_date date not null,
  polo text not null,
  direct_competitors integer not null default 0,
  priority_a integer not null default 0,
  high_overlap integer not null default 0,
  validated_profiles integer not null default 0,
  mapped_competitors integer not null default 0,
  components jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now(),
  primary key (snapshot_date, polo)
);

create table if not exists public.agg_market_opportunities (
  periodo_inicio date not null,
  polo text not null default '',
  uf text not null default '',
  opportunities integer not null default 0,
  high_relevance integer not null default 0,
  total_value numeric,
  avg_relevance_score numeric,
  product_matches jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now(),
  primary key (periodo_inicio, polo, uf)
);

create table if not exists public.agg_market_cockpit (
  periodo_inicio date not null,
  signal_key text not null,
  family text not null default '',
  title text not null,
  classification text not null,
  score integer,
  available_components_count integer not null default 0,
  drivers jsonb not null default '[]'::jsonb,
  target_tab text not null,
  source_periods jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz not null default now(),
  primary key (periodo_inicio, signal_key, family)
);

create index if not exists agg_market_price_pressure_period_idx
  on public.agg_market_price_pressure (periodo_inicio desc, family);

create index if not exists agg_market_demand_family_period_idx
  on public.agg_market_demand_family (periodo_inicio desc, family);

create index if not exists agg_market_opportunities_period_idx
  on public.agg_market_opportunities (periodo_inicio desc, high_relevance desc);

create index if not exists agg_market_cockpit_period_idx
  on public.agg_market_cockpit (periodo_inicio desc, signal_key);

alter table public.market_tab_filter_defaults enable row level security;
alter table public.agg_market_price_pressure enable row level security;
alter table public.agg_market_demand_family enable row level security;
alter table public.agg_market_regional enable row level security;
alter table public.agg_market_competition enable row level security;
alter table public.agg_market_opportunities enable row level security;
alter table public.agg_market_cockpit enable row level security;

drop policy if exists market_tab_filter_defaults_read_public on public.market_tab_filter_defaults;
create policy market_tab_filter_defaults_read_public on public.market_tab_filter_defaults for select to anon, authenticated using (true);

drop policy if exists agg_market_price_pressure_read_public on public.agg_market_price_pressure;
create policy agg_market_price_pressure_read_public on public.agg_market_price_pressure for select to anon, authenticated using (true);

drop policy if exists agg_market_demand_family_read_public on public.agg_market_demand_family;
create policy agg_market_demand_family_read_public on public.agg_market_demand_family for select to anon, authenticated using (true);

drop policy if exists agg_market_regional_read_public on public.agg_market_regional;
create policy agg_market_regional_read_public on public.agg_market_regional for select to anon, authenticated using (true);

drop policy if exists agg_market_competition_read_public on public.agg_market_competition;
create policy agg_market_competition_read_public on public.agg_market_competition for select to anon, authenticated using (true);

drop policy if exists agg_market_opportunities_read_public on public.agg_market_opportunities;
create policy agg_market_opportunities_read_public on public.agg_market_opportunities for select to anon, authenticated using (true);

drop policy if exists agg_market_cockpit_read_public on public.agg_market_cockpit;
create policy agg_market_cockpit_read_public on public.agg_market_cockpit for select to anon, authenticated using (true);

grant select on public.market_tab_filter_defaults to anon, authenticated;
grant select on public.agg_market_price_pressure to anon, authenticated;
grant select on public.agg_market_demand_family to anon, authenticated;
grant select on public.agg_market_regional to anon, authenticated;
grant select on public.agg_market_competition to anon, authenticated;
grant select on public.agg_market_opportunities to anon, authenticated;
grant select on public.agg_market_cockpit to anon, authenticated;

insert into public.market_tab_filter_defaults(tab_key, label, default_months, default_days, filters)
values
  ('market-overview', 'Cockpit', 12, null, '{"shortcut_options":["12M","24M"],"product_family":"ALL"}'::jsonb),
  ('market-prices', 'Preco & Compra', 6, null, '{"shortcut_options":["30D","90D","6M","12M","24M"],"product_family":"ALL","country":"ALL"}'::jsonb),
  ('industry', 'Demanda', 24, null, '{"shortcut_options":["12M","24M","36M"],"product_family":"ALL","economic_segment":"ALL"}'::jsonb),
  ('construction', 'Demanda construcao', 24, null, '{"shortcut_options":["12M","24M","36M"],"product_family":"ALL","economic_segment":"CONSTRUCAO"}'::jsonb),
  ('regional', 'Regional', 12, null, '{"shortcut_options":["12M","24M"],"polo":"ALL"}'::jsonb),
  ('competition', 'Concorrencia', null, null, '{"snapshot":"latest","polo":"ALL","competitor_type":"ALL","priority":"ALL"}'::jsonb),
  ('opportunities', 'Oportunidades', null, 90, '{"shortcut_options":["30D","60D","90D","180D","12M"],"polo":"ALL","uf":"ALL","relevance":"ALL","product_family":"ALL"}'::jsonb),
  ('steel-market', 'Mercado do Aco', 12, null, '{"shortcut_options":["6M","12M","24M"],"product_family":"ALL"}'::jsonb),
  ('imports', 'Importacoes', 12, null, '{"shortcut_options":["6M","12M","24M"],"product_family":"ALL","country":"ALL"}'::jsonb),
  ('solar', 'Solar', 12, null, '{"shortcut_options":["12M","24M"],"uf":"ALL"}'::jsonb)
on conflict (tab_key)
do update set
  label = excluded.label,
  default_months = excluded.default_months,
  default_days = excluded.default_days,
  filters = excluded.filters,
  updated_at = now();
