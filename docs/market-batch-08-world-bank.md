# Batch 08 - World Bank

## Objetivo

Adicionar contexto macro internacional ao modulo Mercado usando a API publica World Bank Indicators v2.

## Implementado

- Criada a migration `20260930103000_market_world_bank.sql`.
- Criadas as tabelas:
  - `raw_world_bank_indicator`
  - `fact_world_bank_macro`
- Criado o coletor `tools/collect_market_world_bank.py`.
- O botao de refresh passou a executar a etapa `market_world_bank`.
- O `market_source_registry` passou a monitorar `world_bank_wdi`.

## Configuracao

Variaveis novas no `.env.example`:

- `WORLD_BANK_API_BASE_URL`
- `WORLD_BANK_COUNTRIES`
- `WORLD_BANK_INDICATORS`
- `WORLD_BANK_START_YEAR`

Padrao atual:

- Paises/regioes: `BRA;CHN;USA;WLD`
- Indicadores:
  - `NY.GDP.MKTP.KD.ZG`
  - `NV.IND.TOTL.KD.ZG`
  - `NV.IND.MANF.KD.ZG`
  - `NE.EXP.GNFS.KD.ZG`
  - `NE.IMP.GNFS.KD.ZG`

## Resultado Validado

- RAW: 520 linhas.
- Fact: 520 linhas.
- `mercado_indicadores`: 362 linhas com valor.
- Periodo carregado: 2000 a 2025.
- Geografias: 4.
- Indicadores: 5.
- Registry: `HEALTHY`.

## Fonte

World Bank Indicators API v2:

- `https://api.worldbank.org/v2`
- Documentacao: `https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures`
