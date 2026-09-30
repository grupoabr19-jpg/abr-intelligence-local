# Batch 07 - ANEEL

## Objetivo

Implantar a ingestao da ANEEL para geracao distribuida fotovoltaica usando o CKAN de dados abertos e mantendo o Supabase leve.

## Implementado

- Criada a migration `20260929211000_market_aneel_solar.sql`.
- Criadas as tabelas:
  - `raw_aneel`
  - `fact_solar_monthly`
- Criado o coletor `tools/collect_market_aneel.py`.
- O coletor descobre o recurso Parquet via CKAN no dataset `relacao-de-empreendimentos-de-geracao-distribuida`.
- O parquet detalhado e agregado por municipio fica preservado no archive.
- O Supabase recebe resumo por `periodo_inicio`, `uf`, `classe` e `fonte`, controlado por `ANEEL_DB_GRAIN=uf`.
- O botao de refresh passou a executar a etapa `market_aneel`.

## Resultado validado

- `raw_aneel`: 15.060 linhas.
- `fact_solar_monthly`: 15.060 linhas.
- `mercado_indicadores` para ANEEL: 45.180 linhas.
- Periodo carregado: 2004-06 a 2026-08.
- Fonte no registry: `HEALTHY`.

## Observacoes

- A fonte ANEEL apresentou instabilidade TLS durante a validacao. O coletor tem retry e tambem suporta recuperacao a partir de um parquet arquivado com `--from-archive-parquet`.
- Registros com periodo operacional anterior a 2000 sao descartados do banco para evitar datas sentinela como `1900-01-01`.
- MW novo e MW acumulado sao calculados sem converter MW em toneladas.
