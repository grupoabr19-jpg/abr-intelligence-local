# Market Batch 04 - Aco Brasil + INDA

Data: 2026-09-29

## Objetivo

Completar a camada RAW/NORMALIZED para Mercado do Aco usando Aco Brasil e INDA, sem criar graficos.

## Implementado

- Criada a tabela `public.raw_aco_brasil`.
- Criada a tabela `public.raw_inda`.
- O coletor `tools/collect_market_sources.py` passou a espelhar indicadores do Aco Brasil em RAW.
- O coletor passou a extrair os percentuais publicos do INDA a partir do HTML.

## Fontes Conectadas

- `aco_brasil_estatistica_mensal`
- `inda_estatisticas`

## Indicadores INDA

Foram extraidos somente percentuais explicitamente publicados:

- compras: variacao mensal e anual;
- vendas: variacao mensal e anual;
- estoque: variacao mensal e anual;
- importacao: variacao mensal e anual.

Nao foi criada tonelagem para INDA porque a pagina publica nao fornece esse dado.

## Validacao

Carga real executada:

- Aco Brasil: 1.804 indicadores em `mercado_indicadores` e 1.804 linhas em `raw_aco_brasil`.
- INDA: 8 indicadores em `mercado_indicadores` e 8 linhas em `raw_inda`.

Status no `market_source_registry`:

- `aco_brasil_estatistica_mensal`: `HEALTHY`, periodo mais recente `2026-08`.
- `inda_estatisticas`: `HEALTHY`, periodo mais recente `JUNHO DE 2026`.

## Arquivos Alterados

- `tools/collect_market_sources.py`
- `supabase/migrations/20260929201000_market_steel_inda_raw.sql`

## Proximo Batch

Batch 05 - CNI Industria + Construcao.
