# Market Batch 05 - CNI Industria + Construcao

Data: 2026-09-29

## Objetivo

Completar a camada RAW para CNI Industria e CNI Construcao usando as planilhas publicas de Serie Recente.

## Implementado

- Criada a tabela `public.raw_cni_industria`.
- Criada a tabela `public.raw_cni_construcao`.
- O coletor `tools/collect_market_sources.py` passou a espelhar os indicadores CNI em RAW.

## Fontes Conectadas

- `cni_sondagem_industrial`
- `cni_sondagem_construcao`

## Validacao

Carga real executada:

- CNI Industria: 1.744 indicadores e 1.744 linhas RAW.
- CNI Construcao: 1.386 indicadores e 1.386 linhas RAW.

Periodos validados:

- CNI Industria: `2007-04` ate `2026-09`.
- CNI Construcao: `2009-12` ate `2026-09`.

Status no `market_source_registry`:

- `cni_sondagem_industrial`: `HEALTHY`.
- `cni_sondagem_construcao`: `HEALTHY`.

## Observacoes

Os indices CNI sao preservados como indices de difusao/atividade. Nenhuma conversao para toneladas foi criada.

## Proximo Batch

Batch 06 - Caged + PNCP.
