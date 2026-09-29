# Market Batch 02 - Fontes API BCB e IBGE

Data: 2026-09-29

## Objetivo

Criar a primeira ingestao API normalizada do modulo Mercado, sem alterar graficos.

## Implementado

- Criada a tabela `public.raw_bcb_ptax`.
- Criada a tabela `public.raw_ibge_sidra`.
- Criado o coletor `tools/collect_market_api_sources.py`.
- O coletor grava RAW, arquiva resposta em JSONL/CSV/Parquet e normaliza dados em `public.mercado_indicadores`.
- O refresh do header passou a executar o passo `market_api` depois do `market_registry`.
- BCB e IBGE foram removidos da lista de fontes pendentes sem coletor ativo.

## Fontes Coletadas

- `bcb_dolar_ptax`
- `ibge_pim_sidra`
- `ibge_construcao_sidra`

## Validacao

Carga executada com sucesso:

- BCB PTAX: 31 registros RAW, 62 indicadores.
- IBGE PIM SIDRA: 972 indicadores.
- IBGE construcao SIDRA: 36 indicadores.
- RAW SIDRA total: 1.008 registros.

Status no `market_source_registry` apos a carga:

- `bcb_dolar_ptax`: `HEALTHY`
- `ibge_pim_sidra`: `HEALTHY`
- `ibge_construcao_sidra`: `HEALTHY`

## Observacoes

- A API SIDRA retorna a dimensao de periodo em campos dinamicos (`D3C` neste path atual), por isso o parser detecta periodo por padrao `YYYYMM`.
- Ainda nao foi criada visualizacao no frontend neste batch.
