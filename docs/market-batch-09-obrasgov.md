# Batch 09 - ObrasGov

## Objetivo

Adicionar sinal de obras publicas ao modulo Mercado usando a nova API publica do ObrasGov.

## Implementado

- Criada a migration `20260930104500_market_obrasgov.sql`.
- Criadas as tabelas:
  - `raw_obrasgov_project_summary`
  - `fact_obrasgov_investments`
- Criado o coletor `tools/collect_market_obrasgov.py`.
- O botao de refresh passou a executar a etapa `market_obrasgov`.
- O `market_source_registry` passou a monitorar `obrasgov_projetos`.

## Configuracao

Variaveis novas:

- `OBRASGOV_API_BASE_URL`
- `OBRASGOV_YEARS`
- `OBRASGOV_PAGE_SIZE`
- `OBRASGOV_MAX_PAGES`

Padrao atual:

- Ano: `2026`
- Tamanho de pagina: `200`
- Limite de paginas: `25`

O limite existe para o refresh nao ficar preso lendo mais de 50 mil projetos em uma execucao comum. Para carga completa, deixe `OBRASGOV_MAX_PAGES` vazio ou aumente o valor no ambiente do coletor.

## Resultado Validado

- Projetos lidos no recorte: 5.000.
- Agregados no Supabase: 358.
- Indicadores em `mercado_indicadores`: 1.074.
- UFs: 27.
- Investimento previsto no recorte: R$ 25.493.312.570,99.
- Registry: `HEALTHY`.

## Fonte

- Portal novo: `https://api-publica.obrasgov.gestao.gov.br`
- OpenAPI: `https://api-publica.obrasgov.gestao.gov.br/obras/openapi.json`
