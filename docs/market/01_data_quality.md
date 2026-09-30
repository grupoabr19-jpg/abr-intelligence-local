# Batch 01 - Qualidade, escalas e unidades

Este batch cria a camada de saneamento dos indicadores de mercado antes da publicacao no dashboard.

## Regras implantadas

- Metadados por fonte e indicador em `public.market_indicator_metadata`.
- Alertas de dados suspeitos em `public.market_data_quality_alerts`.
- Validacao central em `tools/market_indicator_quality.py`.
- Conversao de escala quando o indicador exigir, como Aco Brasil de `mil t` para `t`.
- Preservacao de nulos no backend e no frontend, sem converter ausencia de dado em zero.
- Filtro de publicacao para bloquear indicadores fora da faixa de sanidade.

## Fontes conectadas ao saneamento

- BCB PTAX.
- IBGE SIDRA PIM e construcao.
- ANEEL solar.
- Comex Stat.
- Aco Brasil.
- CNI industria e construcao.
- INDA.
- World Bank.
- ObrasGov.

## Observacoes

Os dados historicos permanecem no banco. A normalizacao de escala passa a ocorrer nos novos ciclos de coleta; na leitura, o dashboard filtra valores fora das regras conhecidas sem alterar linhas antigas.
