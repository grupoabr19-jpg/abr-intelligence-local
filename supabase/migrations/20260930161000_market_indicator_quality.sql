create table if not exists public.market_indicator_metadata (
  source_key text not null,
  indicator_key text not null,
  indicator_name text not null,
  original_unit text,
  normalized_unit text,
  scale_factor numeric not null default 1,
  is_percentage boolean not null default false,
  is_diffusion_index boolean not null default false,
  neutral_value numeric,
  frequency text not null default 'mensal',
  aggregation_method text not null default 'latest',
  min_sanity_value numeric,
  max_sanity_value numeric,
  allow_zero boolean not null default true,
  allow_null boolean not null default true,
  description text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (source_key, indicator_key)
);

create table if not exists public.market_data_quality_alerts (
  id bigserial primary key,
  source text not null,
  indicator text not null,
  period text,
  raw_value numeric,
  normalized_value numeric,
  validation_rule text not null,
  error text not null,
  detected_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb
);

create index if not exists market_data_quality_alerts_detected_idx
  on public.market_data_quality_alerts (detected_at desc, source, indicator);

alter table public.market_indicator_metadata enable row level security;
alter table public.market_data_quality_alerts enable row level security;

drop policy if exists market_indicator_metadata_read_public on public.market_indicator_metadata;
create policy market_indicator_metadata_read_public
  on public.market_indicator_metadata
  for select
  to anon, authenticated
  using (true);

drop policy if exists market_data_quality_alerts_read_public on public.market_data_quality_alerts;
create policy market_data_quality_alerts_read_public
  on public.market_data_quality_alerts
  for select
  to anon, authenticated
  using (true);

grant select on public.market_indicator_metadata to anon, authenticated;
grant select on public.market_data_quality_alerts to anon, authenticated;

insert into public.market_indicator_metadata(
  source_key, indicator_key, indicator_name, original_unit, normalized_unit,
  scale_factor, is_percentage, is_diffusion_index, neutral_value, frequency,
  aggregation_method, min_sanity_value, max_sanity_value, allow_zero, allow_null,
  description
)
values
  ('bcb_dolar_ptax', 'bcb_ptax_cotacaoCompra', 'Dolar PTAX compra', 'BRL/USD', 'BRL/USD', 1, false, false, null, 'diaria', 'latest', 0, 20, false, false, 'Cotacao PTAX compra em reais por dolar. Sanity inicial: 0 < PTAX < 20.'),
  ('bcb_dolar_ptax', 'bcb_ptax_cotacaoVenda', 'Dolar PTAX venda', 'BRL/USD', 'BRL/USD', 1, false, false, null, 'diaria', 'latest', 0, 20, false, false, 'Cotacao PTAX venda em reais por dolar. Sanity inicial: 0 < PTAX < 20.'),
  ('ibge_pim_sidra', 'ibge_pim_producao_fisica', 'IBGE PIM producao fisica', 'indice', 'indice', 1, false, false, null, 'mensal', 'latest', 0, 300, true, false, 'Indice SIDRA/PIM mantido na escala oficial.'),
  ('ibge_construcao_sidra', 'ibge_construcao_indice', 'IBGE construcao indice', 'indice', 'indice', 1, false, false, null, 'mensal', 'latest', 0, 300, true, false, 'Indice SIDRA construcao mantido na escala oficial.'),
  ('aneel_dados_abertos', 'aneel_solar_new_mw', 'ANEEL solar MW novos', 'MW', 'MW', 1, false, false, null, 'mensal', 'sum', 0, null, true, false, 'Potencia mensal ja normalizada para MW pelo coletor.'),
  ('aneel_dados_abertos', 'aneel_solar_cumulative_mw', 'ANEEL solar MW acumulado', 'MW', 'MW', 1, false, false, null, 'mensal', 'sum', 0, null, true, false, 'Potencia acumulada ja normalizada para MW pelo coletor.'),
  ('aneel_dados_abertos', 'aneel_solar_new_installations', 'ANEEL solar novas instalacoes', 'instalacoes', 'instalacoes', 1, false, false, null, 'mensal', 'sum', 0, null, true, false, 'Quantidade de novas instalacoes.'),
  ('comex_stat_ncm', 'comex_import_toneladas', 'Importacoes Comex', 't', 't', 1, false, false, null, 'mensal', 'sum', 0, null, true, false, 'Toneladas importadas calculadas por KG_LIQUIDO / 1000.'),
  ('comex_stat_ncm', 'comex_import_fob_usd_t', 'FOB medio importado', 'US$/t', 'US$/t', 1, false, false, null, 'mensal', 'weighted_average', 0, null, false, true, 'Valor unitario ponderado: SUM(VL_FOB) / SUM(KG_LIQUIDO/1000).'),
  ('comex_stat_ncm', 'comex_import_cif_proxy_usd_t', 'CIF proxy importado', 'US$/t', 'US$/t', 1, false, false, null, 'mensal', 'weighted_average', 0, null, false, true, 'Proxy CIF ponderado: SUM(VL_FOB+VL_FRETE+VL_SEGURO) / toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_producao_aco_bruto', 'Aco bruto', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_producao_laminados', 'Laminados', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_producao_planos', 'Planos', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_producao_longos', 'Longos', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_vendas_internas_total', 'Vendas internas', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_vendas_externas_total', 'Vendas externas', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_exportacoes_total_toneladas', 'Exportacoes totais', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_importacoes_total_toneladas', 'Importacoes totais', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_consumo_aparente_total', 'Consumo aparente', 'mil t', 't', 1000, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Aco Brasil publica em mil toneladas; normalizar para toneladas.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_exportacoes_total_usd', 'Exportacoes totais', 'US$ milhoes', 'US$ milhoes', 1, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Valor em milhoes de dolares.'),
  ('aco_brasil_estatistica_mensal', 'aco_brasil_importacoes_total_usd', 'Importacoes totais', 'US$ milhoes', 'US$ milhoes', 1, false, false, null, 'mensal', 'latest', 0, null, true, false, 'Valor em milhoes de dolares.'),
  ('inda_estatisticas', 'inda_compras_variacao_mes_pct', 'INDA compras variacao mensal', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual mensal publicada pelo INDA.'),
  ('inda_estatisticas', 'inda_compras_variacao_ano_pct', 'INDA compras variacao anual', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual anual publicada pelo INDA.'),
  ('inda_estatisticas', 'inda_vendas_variacao_mes_pct', 'INDA vendas variacao mensal', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual mensal publicada pelo INDA.'),
  ('inda_estatisticas', 'inda_vendas_variacao_ano_pct', 'INDA vendas variacao anual', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual anual publicada pelo INDA.'),
  ('inda_estatisticas', 'inda_estoque_variacao_mes_pct', 'INDA estoque variacao mensal', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual mensal publicada pelo INDA.'),
  ('inda_estatisticas', 'inda_estoque_variacao_ano_pct', 'INDA estoque variacao anual', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual anual publicada pelo INDA.'),
  ('inda_estatisticas', 'inda_importacao_variacao_mes_pct', 'INDA importacao variacao mensal', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual mensal publicada pelo INDA.'),
  ('inda_estatisticas', 'inda_importacao_variacao_ano_pct', 'INDA importacao variacao anual', '%', '%', 1, true, false, null, 'mensal', 'latest', -100, 100, true, false, 'Variacao percentual anual publicada pelo INDA.'),
  ('world_bank_wdi', 'world_bank_NY.GDP.MKTP.KD.ZG', 'World Bank GDP growth', '%', '%', 1, true, false, null, 'anual', 'latest', -100, 100, true, true, 'Crescimento anual do PIB em percentual.'),
  ('world_bank_wdi', 'world_bank_NV.IND.TOTL.KD.ZG', 'World Bank industry growth', '%', '%', 1, true, false, null, 'anual', 'latest', -100, 100, true, true, 'Crescimento anual da industria em percentual.'),
  ('world_bank_wdi', 'world_bank_NV.IND.MANF.KD.ZG', 'World Bank manufacturing growth', '%', '%', 1, true, false, null, 'anual', 'latest', -100, 100, true, true, 'Crescimento anual da manufatura em percentual.'),
  ('world_bank_wdi', 'world_bank_NE.EXP.GNFS.KD.ZG', 'World Bank exports growth', '%', '%', 1, true, false, null, 'anual', 'latest', -100, 100, true, true, 'Crescimento anual de exportacoes em percentual.'),
  ('world_bank_wdi', 'world_bank_NE.IMP.GNFS.KD.ZG', 'World Bank imports growth', '%', '%', 1, true, false, null, 'anual', 'latest', -100, 100, true, true, 'Crescimento anual de importacoes em percentual.')
on conflict (source_key, indicator_key)
do update set
  indicator_name = excluded.indicator_name,
  original_unit = excluded.original_unit,
  normalized_unit = excluded.normalized_unit,
  scale_factor = excluded.scale_factor,
  is_percentage = excluded.is_percentage,
  is_diffusion_index = excluded.is_diffusion_index,
  neutral_value = excluded.neutral_value,
  frequency = excluded.frequency,
  aggregation_method = excluded.aggregation_method,
  min_sanity_value = excluded.min_sanity_value,
  max_sanity_value = excluded.max_sanity_value,
  allow_zero = excluded.allow_zero,
  allow_null = excluded.allow_null,
  description = excluded.description,
  updated_at = now();

insert into public.market_indicator_metadata(
  source_key, indicator_key, indicator_name, original_unit, normalized_unit,
  scale_factor, is_percentage, is_diffusion_index, neutral_value, frequency,
  aggregation_method, min_sanity_value, max_sanity_value, allow_zero, allow_null,
  description
)
select distinct
  mi.source_key,
  mi.indicador_key,
  max(mi.indicador_nome),
  max(mi.unidade),
  max(mi.unidade),
  1,
  bool_or(mi.unidade = '%'),
  bool_or(mi.unidade = 'indice'),
  case when bool_or(mi.unidade = 'indice') then 50::numeric else null end,
  'mensal',
  'latest',
  case
    when bool_or(mi.unidade = '%') then -100::numeric
    when bool_or(mi.unidade = 'indice') then 0::numeric
    else null
  end,
  case
    when bool_or(mi.unidade = '%') then 100::numeric
    when bool_or(mi.unidade = 'indice') then 100::numeric
    else null
  end,
  true,
  true,
  'Metadata inicial inferida de mercado_indicadores. Revisar no Batch 01+.'
from public.mercado_indicadores mi
where not exists (
  select 1
  from public.market_indicator_metadata mim
  where mim.source_key = mi.source_key
    and mim.indicator_key = mi.indicador_key
)
group by mi.source_key, mi.indicador_key;
