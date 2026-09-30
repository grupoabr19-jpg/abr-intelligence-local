# Batches 08 e 09 - World Bank e ObrasGov

## Batch 08

Conecta World Bank ao cockpit decisorio de Mercado.

- Usa `fact_world_bank_macro`.
- Cria sinal `macro_industrial_context`.
- Avalia indicadores de crescimento de PIB, industria e manufatura para Brasil, China e Mundo.
- Classifica:
  - `FAVORAVEL` quando o score agregado e positivo o suficiente;
  - `DESFAVORAVEL` quando o score agregado e negativo;
  - `MISTO / NEUTRO` nos demais casos;
  - `INSUFFICIENT_DATA` se houver menos de 3 componentes.
- A visao geral de Mercado passa a destacar o sinal macro industrial.

## Batch 09

Conecta ObrasGov ao cockpit decisorio de Mercado.

- Usa `fact_obrasgov_investments`.
- Cria sinal `public_works_pipeline`.
- Consolida projetos, investimento previsto, empregos estimados e UFs no periodo mais recente.
- Classifica:
  - `ALTA OPORTUNIDADE` para investimento >= R$ 10 bi;
  - `OPORTUNIDADE MODERADA` para investimento >= R$ 1 bi;
  - `BAIXA OPORTUNIDADE` abaixo disso;
  - `INSUFFICIENT_DATA` sem projetos.
- A aba Construcao passa a exibir o sinal ObrasGov.

## Validacao

Estado validado em 2026-09-30:

- `raw_world_bank_indicator`: 520 linhas;
- `fact_world_bank_macro`: 520 linhas;
- `raw_obrasgov_project_summary`: 343 linhas;
- `fact_obrasgov_investments`: 343 linhas;
- `market_source_registry.world_bank_wdi`: `HEALTHY`;
- `market_source_registry.obrasgov_projetos`: `HEALTHY`;
- `agg_market_cockpit`: 11 sinais apos incluir World Bank e ObrasGov.
