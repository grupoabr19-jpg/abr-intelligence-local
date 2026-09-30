# Batches 02 e 03 - Filtros e camada decisoria

## Batch 02

Cria a infraestrutura para filtros independentes por sub-aba de Mercado:

- defaults por aba em `market_tab_filter_defaults`;
- cada aba de Mercado passa a ter periodo proprio no frontend;
- `date_to` e tratado como data de corte da aba ativa;
- o filtro global deixa de controlar Mercado diretamente.

## Batch 03

Cria a primeira camada analitica orientada a decisao:

- `agg_market_price_pressure`;
- `agg_market_demand_family`;
- `agg_market_regional`;
- `agg_market_competition`;
- `agg_market_opportunities`;
- `agg_market_cockpit`;
- script `tools/refresh_market_decision_aggs.py`.

Os agregados usam somente componentes disponiveis e mantem status `INSUFFICIENT_DATA` quando ha menos de tres drivers validos.
