# Market Batch 03 - Comex Stat

Data: 2026-09-29

## Objetivo

Preparar a ingestao Comex Stat sem inventar NCMs de aco.

## Implementado

- Criada a dimensao `public.dim_ncm_abr`.
- Criada a tabela RAW `public.raw_comex_import`.
- Criada a fato mensal `public.fact_steel_import_monthly`.
- Criado o coletor `tools/collect_market_comex.py`.
- O refresh do header passou a executar `market_comex`.

## Regra de Seguranca

O coletor nao baixa nem processa `IMP_{ANO}.csv` enquanto `dim_ncm_abr` nao tiver NCM ativo aprovado.

Isto evita:

- classificar NCM automaticamente;
- trazer importacao que nao pertence ao escopo ABR;
- criar indicador oficial com dado nao validado.

## Calculos Preparados

- `toneladas = KG_LIQUIDO / 1000`
- `fob_usd_t = SUM(VL_FOB) / SUM(toneladas)`
- `cif_proxy_usd_t = SUM(VL_FOB + VL_FRETE + VL_SEGURO) / SUM(toneladas)`

Todos os valores unitarios usam media ponderada por peso.

## Validacao

Execucao realizada:

```text
status: sem_ncm_aprovado
message: Cadastre NCMs ativos em dim_ncm_abr antes de processar Comex.
```

Este e o resultado esperado enquanto nao houver mapeamento aprovado de NCM.

## Pendencia

Cadastrar NCMs aprovados em `dim_ncm_abr` com:

- `ncm`
- `descricao`
- `familia_abr`
- `subfamilia_abr`
- `ativo`
- `vigencia_inicio`
- `vigencia_fim`

Somente depois disso a fonte Comex podera ficar `HEALTHY`.
