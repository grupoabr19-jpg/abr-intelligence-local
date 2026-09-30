# Batches 06 e 07 - Governo e ANEEL

## Batch 06

Valida o estado seguro das fontes CAGED e PNCP.

- CAGED permanece sem ingestao enquanto `dim_cnae_abr` nao tiver CNAEs ativos aprovados.
- PNCP permanece sem consulta enquanto `pncp_modality_codes` nao tiver modalidades ativas aprovadas.
- O coletor `tools/collect_market_gov_sources.py --source all --dry-run` retorna:
  - `caged_microdados`: `sem_cnae_aprovado`;
  - `pncp_consulta`: `sem_modalidade_aprovada`.

Esse bloqueio e intencional para nao baixar microdados grandes nem classificar oportunidade publica sem regra aprovada.

## Batch 07

Conecta ANEEL ao cockpit decisorio de Mercado.

- Usa `fact_solar_monthly` como base agregada.
- Calcula sinal `solar_momentum` comparando MW novos dos ultimos 12 meses contra os 12 meses anteriores.
- Classifica:
  - `EXPANSAO` se atual >= anterior * 1,15;
  - `DESACELERANDO` se atual <= anterior * 0,85;
  - `ESTAVEL` nos demais casos;
  - `INSUFFICIENT_DATA` se nao houver base anterior.
- A aba Solar passa a exibir o sinal 12M.

## Validacao

Estado validado em 2026-09-30:

- `raw_aneel`: 15.060 linhas;
- `fact_solar_monthly`: 15.060 linhas;
- `market_source_registry.aneel_dados_abertos`: `HEALTHY`;
- `agg_market_cockpit`: 9 sinais apos incluir `solar_momentum`.
