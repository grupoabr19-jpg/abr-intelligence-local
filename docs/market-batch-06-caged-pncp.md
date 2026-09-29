# Market Batch 06 - CAGED + PNCP

Data: 2026-09-29

## Objetivo

Preparar CAGED e PNCP sem carregar microdados grandes nem classificar oportunidades sem configuracao aprovada.

## Implementado

- Criada `public.dim_cnae_abr`.
- Criada `public.pncp_modality_codes`.
- Criada `public.raw_caged`.
- Criada `public.fact_employment_monthly`.
- Criada `public.raw_pncp`.
- Criada `public.fact_pncp_opportunities`.
- Criado `tools/collect_market_gov_sources.py`.
- O refresh do header passou a executar `market_gov`.

## Regras de Seguranca

CAGED:

- nao baixa microdados se `dim_cnae_abr` estiver vazia;
- evita gravar dados individuais desnecessarios;
- a tabela analitica preparada e mensal/agregada.

PNCP:

- nao consulta oportunidades se `pncp_modality_codes` estiver vazia;
- nao inventa modalidade;
- calcula `relevance_score` apenas por termos configurados no coletor.

## Validacao

Execucao realizada:

```text
caged_microdados: sem_cnae_aprovado
pncp_consulta: sem_modalidade_aprovada
```

Contagens apos execucao:

- `dim_cnae_abr`: 0
- `pncp_modality_codes`: 0
- `raw_caged`: 0
- `raw_pncp`: 0
- `fact_pncp_opportunities`: 0

Este e o comportamento esperado ate o cadastro das configuracoes aprovadas.

## Pendencias

- Cadastrar CNAEs aprovados em `dim_cnae_abr`.
- Cadastrar modalidades PNCP aprovadas em `pncp_modality_codes`.
- Depois disso, executar novamente o coletor governamental.

## Proximo Batch

Batch 07 - ANEEL.
