# Batches 04 e 05 - Drivers Aco/INDA/CNI

## Batch 04

Conecta Aco Brasil e INDA a camada decisoria de preco e compra.

- Aco Brasil entra como demanda siderurgica nacional por consumo aparente e vendas internas.
- INDA entra como sinal de estoque do distribuidor, usando variacao mensal e anual.
- Cada componente usa o periodo mais recente disponivel ate a data de corte da aba.
- `source_periods` registra a defasagem por fonte para evitar misturar silencio de fonte com dado inexistente.

## Batch 05

Conecta CNI Industria e CNI Construcao a camada decisoria de demanda por familia.

- CNI Industria passa a fornecer multiplos drivers de demanda industrial.
- CNI Construcao passa a fornecer multiplos drivers de demanda de construcao.
- IBGE, Aco Brasil e INDA complementam o score quando houver dados validos.
- O frontend exibe a tabela "Demanda por familia" na aba Industria.

## Validacao esperada

Ao executar `tools/refresh_market_decision_aggs.py`, espera-se:

- `agg_market_price_pressure` com 4 familias e status diferente de `INSUFFICIENT_DATA` quando houver pelo menos 3 componentes validos;
- `agg_market_demand_family` com 4 familias e drivers CNI/IBGE/Aco/INDA rastreados;
- `agg_market_cockpit` refletindo os sinais recalculados.
