# Market Batch 00 - Auditoria da Implementacao Atual

Data da auditoria: 2026-09-29

## Objetivo

Auditar o estado atual do modulo Mercado antes de iniciar novos batches.

## Estado Atual

O projeto ja possui uma primeira estrutura de mercado criada em `supabase/migrations/20260924203000_market_external_sources.sql`.

Tabelas existentes:

- `public.mercado_fontes`
- `public.mercado_coletas`
- `public.mercado_documentos`
- `public.mercado_indicadores`

Ainda nao existe:

- `public.market_source_registry`
- tabelas raw especificas como `raw_bcb_ptax`, `raw_ibge_sidra`, `raw_comex_import`
- agregados oficiais como `agg_market_overview_monthly`, `agg_steel_market_monthly`, `agg_industry_monthly`

## Fontes Cadastradas

Fontes em `mercado_fontes`:

- `aco_brasil_estatistica_mensal`
- `bcb_dolar_ptax`
- `cni_sondagem_construcao`
- `cni_sondagem_industrial`
- `ibge_pim_sidra`
- `inda_estatisticas`

Observacao: BCB e IBGE estao cadastrados como fonte, mas ainda nao possuem coletor/indicadores persistidos nas tabelas atuais.

## Coletores Existentes

Arquivo principal:

- `tools/collect_market_sources.py`

Fontes atualmente coletadas pelo script:

- Aco Brasil
- CNI Industria
- CNI Construcao
- INDA

O script:

- descobre documentos nas paginas publicas;
- grava documentos em `mercado_documentos`;
- arquiva no Drive/local via `backend.archive_storage`;
- extrai indicadores de planilhas para `mercado_indicadores` para Aco Brasil e CNI.

## Dados Encontrados no Banco

Ultima coleta bem-sucedida: `2026-09-29 15:35:23 UTC`.

Indicadores atuais:

- Aco Brasil: 1.804 indicadores, periodo de `2013-01` a `2026-08`
- CNI Construcao: 1.386 indicadores, periodo de `2009-12` a `2026-09`
- CNI Industria: 1.744 indicadores, periodo de `2007-04` a `2026-09`

INDA:

- possui documento/pagina coletada;
- nao possui indicadores normalizados em `mercado_indicadores`.

Falhas historicas:

- CNI Industria e CNI Construcao tiveram alguns `ReadTimeout`, mas a ultima coleta esta com sucesso.

## Frontend

As abas de Mercado ja existem no enum e na navegacao:

- Visao Geral
- Mercado do Aco
- Precos
- Importacoes
- Construcao
- Industria
- Agro
- Solar
- Regional
- Concorrencia
- Usinas

Porem, atualmente o frontend renderiza `UnavailableTab` para Mercado, exceto concorrencia. Ou seja, nao ha painel real consumindo `mercado_indicadores`.

## Variaveis de Ambiente

`.env.example` possui variaveis para:

- BCB
- IBGE PIM
- ANEEL
- Comex
- Aco Brasil
- CNI
- INDA
- Caged
- PNCP

Pendencias no example:

- `IBGE_CONSTRUCTION_TABLE_ID`
- `IBGE_CONSTRUCTION_DEFAULT_PATH`
- `COMEX_STAT_CSV_BASE_URL` esta vazio no example, enquanto o prompt define a URL publica.

## Divergencias Frente ao Prompt Mestre

- O prompt pede `market_source_registry`, mas o sistema atual usa `mercado_fontes` + `mercado_coletas`.
- O prompt pede status padronizado `DISABLED`, `CONFIGURED`, `HEALTHY`, `STALE`, `ERROR`; ainda nao existe essa camada.
- O prompt pede nao mostrar abas sem fontes saudaveis; o frontend hoje esconde quase tudo de mercado, mas nao faz isso dinamicamente por fonte.
- O prompt pede camada RAW/NORMALIZED/FACT/AGGREGATED; hoje existe uma camada unica de documentos e indicadores para algumas fontes publicas.
- BCB e IBGE estao cadastrados, mas ainda nao coletados.
- INDA e coletado como pagina, mas nao normalizado como indicador.

## Recomendacao para o Proximo Batch

Executar o Batch 01:

- criar `market_source_registry`;
- criar health check por fonte;
- preencher status de disponibilidade usando as fontes configuradas;
- nao criar graficos ainda.

O Batch 01 deve reaproveitar `mercado_fontes`, `mercado_coletas`, `mercado_documentos` e `mercado_indicadores` quando fizer sentido, sem apagar historico.
