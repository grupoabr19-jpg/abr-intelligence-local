# ABR Intelligence - Mercado - Batch 00 Current Audit

Data da auditoria: 2026-09-30

## Escopo

Este documento executa o BATCH 00 da reconstrucao do modulo Mercado.
Nao houve alteracao de regra de negocio neste batch.

Objetivo do batch:

- mapear componentes atuais;
- mapear APIs;
- mapear coletores;
- mapear tabelas;
- mapear normalizacoes;
- mapear unidades;
- mapear indicadores;
- mapear filtros;
- mapear funcoes de agregacao;
- mapear rotas;
- mapear cache;
- mapear estado de frontend;
- mapear estrutura atual das sub-abas.

## Resumo Executivo

O modulo Mercado ja possui uma base tecnica relevante: registry de fontes, coletores externos, tabelas raw/fact para varias fontes, orquestrador de refresh e telas no frontend.

O problema principal nao e ausencia total de integracao. O problema e que o modelo atual ainda esta misturado entre:

- telas por fonte ou instituicao;
- indicadores sem metadata formal de escala/unidade;
- filtros globais compartilhados com outras areas do dashboard;
- visao geral com informacao operacional de saude de fonte;
- regras de decisao ainda nao materializadas em agregados orientados a Compra, Preco, Demanda, Regional, Concorrencia e Prospeccao.

## Estado Atual Observado no Backend

### Rotas

Arquivo: `backend/api/main.py`

Rotas relevantes:

- `GET /health`
- `GET /v1/dashboard/internal`
- `POST /v1/dashboard/refresh`
- `GET /v1/dashboard/refresh`
- `GET /v1/aster/reports`
- `GET /v1/aster/requirements`
- `GET /v1/intelligence/domains`
- `GET /v1/sales/regions-summary`

O modulo Mercado nao possui endpoint dedicado. Ele e entregue dentro de:

- `internal_dashboard_summary()`
- `market_summary()`

Arquivo principal:

- `backend/api/data.py`

### Refresh e Jobs

Arquivo: `backend/api/update_orchestrator.py`

Passos de Mercado executados pelo refresh:

- `market_registry`: `tools/refresh_market_source_registry.py`
- `market_api`: `tools/collect_market_api_sources.py`
- `market_aneel`: `tools/collect_market_aneel.py`
- `market_world_bank`: `tools/collect_market_world_bank.py`
- `market_obrasgov`: `tools/collect_market_obrasgov.py`
- `market_comex`: `tools/collect_market_comex.py`
- `market_gov`: `tools/collect_market_gov_sources.py`
- `market_public`: `tools/collect_market_sources.py`

O refresh tambem executa fontes que nao pertencem apenas ao modulo Mercado:

- Kommo;
- Atendimento facts;
- Google Drive spreadsheets;
- Aster ERP;
- cache comercial.

Risco atual:

- o botao de refresh e global;
- o filtro de data enviado para o refresh tambem e global;
- a especificacao nova exige filtros independentes por sub-aba de Mercado.

## Estado Atual Observado no Frontend

Arquivo: `frontend/src/App.tsx`

### Estado Global

Estados globais relevantes:

- `macroArea`
- `intelligenceTab`
- `dateFrom`
- `dateTo`
- `statusFilter`
- `areaFilter`
- `search`
- `refreshMessage`
- `refreshingSources`

Problema frente a especificacao:

- `dateFrom` e `dateTo` sao compartilhados por negocio, mercado e atendimento;
- Mercado nao possui estado proprio por sub-aba;
- o botao `Aplicar` afeta a tela inteira;
- o botao refresh usa o mesmo intervalo global.

### Navegacao Atual de Mercado

Apos a ultima alteracao, o menu de Mercado no frontend esta definido como:

- Visao Geral
- Mercado do Aco
- Precos & Cambio
- Importacoes
- Industria
- Construcao
- Regional
- Concorrencia
- Oportunidades
- Solar

Abas ocultas/removidas da navegacao:

- Agro
- Usinas

Observacao:

- a nova especificacao substitui essa navegacao por uma navegacao orientada a decisao:
  - Cockpit
  - Preco & Compra
  - Demanda
  - Regional
  - Concorrencia
  - Oportunidades
  - Dados & Fontes fora da navegacao comercial principal

### Renderizacao Atual

Componentes atuais de Mercado:

- `MarketTab`
- `MarketOverview`
- `MarketIndicatorTab`
- `MarketPricesTab`
- `MarketImportsTab`
- `MarketConstructionTab`
- `MarketOpportunitiesTab`
- `MarketSolarTab`

Problema frente a especificacao:

- `MarketOverview` ainda mostra saude de fontes, linhas carregadas e ultimos periodos;
- isso deve migrar para `Dados & Fontes`;
- Cockpit ainda nao existe;
- Preco & Compra ainda nao calcula score decisorio;
- Demanda ainda nao calcula sinal por familia;
- Regional e Concorrencia ainda nao possuem implementacao real.

## Contrato Atual da API do Frontend

Arquivo: `frontend/src/api.ts`

`DashboardSummary.market_summary` contem:

- `sources`
- `healthy_sources`
- `available_tabs`
- `overview`
- `steel_market`
- `prices`
- `imports`
- `construction`
- `industry`
- `opportunities`
- `solar`

Pontos de risco:

- o contrato ainda expõe blocos por fonte/area original;
- ainda nao existe contrato para Cockpit, Preco & Compra, Demanda, Regional, Concorrencia orientados a decisao;
- nao ha metadata de indicador no payload;
- nao ha informacao padronizada de `available_components_count` ou `INSUFFICIENT_DATA`.

## Estado Atual do Banco e Fontes

Consulta executada via `market_summary()` em 2026-09-30.

Abas atuais retornadas:

- `market-overview`
- `steel-market`
- `market-prices`
- `industry`
- `construction`
- `opportunities`
- `solar`

Fontes saudaveis:

- `aco_brasil_estatistica_mensal`
- `aneel_dados_abertos`
- `bcb_dolar_ptax`
- `cni_sondagem_construcao`
- `cni_sondagem_industrial`
- `ibge_construcao_sidra`
- `ibge_pim_sidra`
- `inda_estatisticas`
- `obrasgov_projetos`
- `world_bank_wdi`

Fontes configuradas sem dados validos:

- `caged_microdados`
- `comex_stat_ncm`
- `pncp_consulta`

Snapshot observado:

| Fonte | Status | Periodo mais recente | Linhas |
|---|---:|---:|---:|
| Aco Brasil | HEALTHY | 2026-08 | 1804 |
| ANEEL | HEALTHY | 2026-08 | 45180 |
| BCB PTAX | HEALTHY | 2026-09-29 | 62 |
| CNI Construcao | HEALTHY | 2026-09 | 1386 |
| CNI Industria | HEALTHY | 2026-09 | 1744 |
| IBGE Construcao | HEALTHY | setembro 2025 | 36 |
| IBGE PIM | HEALTHY | setembro 2025 | 972 |
| INDA | HEALTHY | JUNHO DE 2026 | 8 |
| ObrasGov | HEALTHY | 2026 | 1029 |
| World Bank | HEALTHY | 2025 | 362 |
| CAGED | CONFIGURED | sem dado | 0 |
| Comex | CONFIGURED | sem dado | 0 |
| PNCP | CONFIGURED | sem dado | 0 |

## Tabelas de Mercado Mapeadas

### Camada de Registry e Indicadores

Migrations:

- `supabase/migrations/20260924203000_market_external_sources.sql`
- `supabase/migrations/20260929190000_market_source_registry.sql`

Tabelas:

- `mercado_fontes`
- `mercado_coletas`
- `mercado_documentos`
- `mercado_indicadores`
- `market_source_registry`

Status:

- registry existe;
- status padronizados existem: `DISABLED`, `CONFIGURED`, `HEALTHY`, `STALE`, `ERROR`;
- ainda nao existe metadata formal por indicador para escala/unidade.

### BCB e IBGE

Migration:

- `supabase/migrations/20260929193000_market_raw_api_sources.sql`

Tabelas:

- `raw_bcb_ptax`
- `raw_ibge_sidra`

Coletores:

- `tools/collect_market_api_sources.py`

Indicadores:

- `bcb_ptax_cotacaoCompra`
- `bcb_ptax_cotacaoVenda`
- `ibge_pim_producao_fisica`
- `ibge_construcao_indice`

Riscos:

- PTAX precisa de teste de sanidade `0 < valor < 20`;
- IBGE precisa de metadata de unidade/escala;
- valores nulos devem permanecer nulos.

### Aco Brasil e INDA

Migration:

- `supabase/migrations/20260929201000_market_steel_inda_raw.sql`

Tabelas:

- `raw_aco_brasil`
- `raw_inda`

Coletor:

- `tools/collect_market_sources.py`

Riscos:

- Aco Brasil pode publicar valores em mil toneladas;
- dashboard atual usa `mil t` como fallback visual;
- nao ha tabela de metadata definindo raw unit, normalized unit e scale factor;
- INDA possui poucos registros e deve ser usado como driver, nao como tonelagem inventada.

### CNI

Migration:

- `supabase/migrations/20260929203000_market_cni_raw.sql`

Tabelas:

- `raw_cni_industria`
- `raw_cni_construcao`

Coletor:

- `tools/collect_market_sources.py`

Riscos:

- indices de difusao precisam manter escala oficial;
- neutralidade 50 deve vir de metadata;
- nao ha validacao formal contra multiplicacao por 10;
- CNI UCI percentual e indices de difusao misturam sem metadata central.

### Comex

Migration:

- `supabase/migrations/20260929195000_market_comex_stat.sql`

Tabelas:

- `dim_ncm_abr`
- `raw_comex_import`
- `fact_steel_import_monthly`

Coletor:

- `tools/collect_market_comex.py`

Indicadores:

- `comex_import_toneladas`
- `comex_import_fob_usd_t`
- `comex_import_cif_proxy_usd_t`

Status atual:

- fonte `comex_stat_ncm` esta `CONFIGURED`;
- sem linhas validas;
- a aba `Importacoes` nao aparece atualmente.

Pontos corretos ja existentes:

- FOB US$/t e calculado por ponderacao: `SUM(VL_FOB) / SUM(KG_LIQUIDO / 1000)`;
- CIF proxy tambem usa soma ponderada.

Pendencias:

- preencher/aprovar `dim_ncm_abr`;
- criar metadata de sanity;
- criar score de pressao por familia;
- nao publicar sem NCM aprovado.

### ANEEL / Solar

Migration:

- `supabase/migrations/20260929211000_market_aneel_solar.sql`

Tabelas:

- `raw_aneel`
- `fact_solar_monthly`

Coletor:

- `tools/collect_market_aneel.py`

Conversao observada:

- codigo divide `potencia_kw / 1000` para gerar MW.

Risco:

- a unidade original precisa ser explicitada em metadata;
- hoje a conversao assume kW pela coluna;
- a especificacao exige nao assumir unidade pelo nome.

### CAGED e PNCP

Migration:

- `supabase/migrations/20260929205000_market_caged_pncp.sql`

Tabelas:

- `dim_cnae_abr`
- `pncp_modality_codes`
- `raw_caged`
- `fact_employment_monthly`
- `raw_pncp`
- `fact_pncp_opportunities`

Coletor:

- `tools/collect_market_gov_sources.py`

Status atual:

- `caged_microdados` esta `CONFIGURED`, sem dado;
- `pncp_consulta` esta `CONFIGURED`, sem dado.

Riscos:

- PNCP ainda nao filtra obrigatoriamente territorio comercial ABR;
- relevance score existe no fato, mas a configuracao de pesos por termo/produto ainda nao esta formalizada em tabela;
- oportunidades nacionais nao devem virar KPI comercial principal.

### ObrasGov

Migration:

- `supabase/migrations/20260930104500_market_obrasgov.sql`

Tabelas:

- `raw_obrasgov_project_summary`
- `fact_obrasgov_investments`

Coletor:

- `tools/collect_market_obrasgov.py`

Status atual:

- `obrasgov_projetos` esta `HEALTHY`;
- periodo 2026;
- 1029 linhas.

Risco:

- resumo e nacional/UF;
- nao substitui oportunidades comerciais concretas por polo;
- deve ser driver de Oportunidades/Regional, nao KPI bruto sem contexto.

### World Bank

Migration:

- `supabase/migrations/20260930103000_market_world_bank.sql`

Tabelas:

- `raw_world_bank_indicator`
- `fact_world_bank_macro`

Coletor:

- `tools/collect_market_world_bank.py`

Status:

- `world_bank_wdi` esta `HEALTHY`.

Riscos:

- percentuais macro podem vir como `0.023`, `2.3` ou `%`;
- nao ha metadata formal para impedir multiplicacao dupla.

## Normalizacao, Unidades e Escalas

Hoje as normalizacoes ficam espalhadas entre:

- coletores Python;
- `market_summary()` no backend;
- formatadores do frontend (`marketValue`, `percent`, `marketNumber`);
- fallback visual por componente.

Problemas tecnicos observados:

- nao existe `market_indicator_metadata`;
- nao existe `market_data_quality_alerts`;
- nao existe `validate_indicator_value()` central;
- metadata de unidade/escala fica implicita no codigo;
- `market_decimal(None)` retorna `"0"`, o que e perigoso para componentes que deveriam preservar null;
- `numericValue()` no frontend converte `null/undefined` para `0`, o que pode criar queda artificial se usado em series;
- `market_indicator_series()` usa `avg(valor)`, o que pode ser incorreto para indicadores que exigem soma ponderada;
- `MarketIndicatorTab` transforma toda serie em numero via `numericValue`, logo null futuro viraria 0.

## Filtros

Estado atual:

- filtros ficam no topo do dashboard;
- `dateFrom` e `dateTo` sao globais;
- `statusFilter`, `areaFilter` e `search` tambem sao globais;
- Mercado nao possui filtro proprio por sub-aba.

Requisito futuro:

- filtros devem ficar abaixo das sub-abas de Mercado;
- cada sub-aba deve preservar seu proprio periodo;
- `Aplicar` deve afetar somente a aba ativa;
- `Restaurar padrao` deve afetar somente a aba ativa.

## Cache

Cache explicitamente identificado:

- `dashboard_sales_summary_cache`

Mercado ainda depende de:

- tabelas fact/raw;
- `mercado_indicadores`;
- `market_source_registry`;
- resposta calculada em `market_summary()`.

Nao foi identificado cache especifico para agregados decisorios de Mercado.

## Agregacoes Decisorias

Ainda nao existem:

- `agg_market_price_pressure`
- `agg_market_demand_family`
- `agg_market_regional`
- `agg_market_competition`
- `agg_market_opportunities`
- `agg_market_cockpit`

Agregados/facts existentes sao por fonte:

- `fact_steel_import_monthly`
- `fact_solar_monthly`
- `fact_employment_monthly`
- `fact_pncp_opportunities`
- `fact_obrasgov_investments`
- `fact_world_bank_macro`

Conclusao:

- a base esta preparada para iniciar a camada decisoria;
- a camada decisoria ainda nao existe.

## Principais Riscos de Qualidade

### Critico

1. Null tratado como zero em formatadores e series.
   - Risco: quedas artificiais nos graficos.
   - Evidencia: `numericValue(null)` retorna 0; `market_decimal(None)` retorna "0".

2. Ausencia de metadata central de indicador.
   - Risco: escala/unidade definida por inferencia ou fallback visual.
   - Evidencia: nao existe `market_indicator_metadata`.

3. Filtros globais para Mercado.
   - Risco: periodo de compra/preco, demanda e oportunidades ficam semanticamente misturados.
   - Evidencia: `dateFrom/dateTo` ficam no estado global de `App`.

### Alto

4. Visao Geral ainda exibe saude tecnica de fontes.
   - Risco: a primeira tela nao responde "o que merece atencao hoje".
   - Evidencia: `MarketOverview` renderiza fontes saudaveis, linhas e registry.

5. Dados por fonte ainda aparecem como abas comerciais.
   - Risco: modulo responde "qual fonte tenho" em vez de "qual decisao investigar".
   - Evidencia: abas `Mercado do Aco`, `Industria`, `Construcao`, `Solar`.

6. Oportunidades ainda usam ObrasGov como fallback nacional.
   - Risco: KPI pode mostrar projetos nacionais sem aderencia ao territorio ABR.
   - Evidencia: `market_opportunities_summary()` cai para `market_obrasgov_summary()` quando PNCP nao tem dado.

### Medio

7. Comex configurado sem dados.
   - Risco: Preco & Compra fica sem familia/importacao ate `dim_ncm_abr` ser aprovada.

8. CAGED e PNCP configurados sem linhas.
   - Risco: Demanda, Regional e Oportunidades ficam com baixa cobertura.

9. ANEEL convertido assumindo kW.
   - Risco: erro se fonte mudar unidade ou coluna.

## Validacoes Executadas

Comandos/checagens executados:

- leitura do novo prompt de batch;
- varredura de rotas em `backend/api/main.py`;
- varredura de estado/filtros em `frontend/src/App.tsx`;
- varredura de contrato em `frontend/src/api.ts`;
- varredura de migrations de Mercado em `supabase/migrations`;
- varredura de coletores `tools/collect_market*.py`;
- execucao de `market_summary()` contra o banco configurado.

Resultado da chamada `market_summary()`:

- executou com sucesso;
- retornou fontes saudaveis e configuradas;
- confirmou Comex e PNCP ainda sem dado valido;
- confirmou que Solar esta ativa quando ANEEL esta saudavel.

## Arquivos Mapeados

Backend:

- `backend/api/main.py`
- `backend/api/data.py`
- `backend/api/update_orchestrator.py`
- `backend/api/config.py`
- `backend/api/models.py`

Frontend:

- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/styles.css`

Coletores:

- `tools/refresh_market_source_registry.py`
- `tools/collect_market_api_sources.py`
- `tools/collect_market_sources.py`
- `tools/collect_market_comex.py`
- `tools/collect_market_aneel.py`
- `tools/collect_market_world_bank.py`
- `tools/collect_market_obrasgov.py`
- `tools/collect_market_gov_sources.py`

Migrations principais:

- `20260924203000_market_external_sources.sql`
- `20260929190000_market_source_registry.sql`
- `20260929193000_market_raw_api_sources.sql`
- `20260929195000_market_comex_stat.sql`
- `20260929201000_market_steel_inda_raw.sql`
- `20260929203000_market_cni_raw.sql`
- `20260929205000_market_caged_pncp.sql`
- `20260929211000_market_aneel_solar.sql`
- `20260930103000_market_world_bank.sql`
- `20260930104500_market_obrasgov.sql`

## Conclusao do Batch 00

O modulo Mercado tem conectores e tabelas suficientes para evoluir, mas a camada atual ainda e orientada a fonte.

Para a reconstrucao orientada a decisao, o proximo batch deve atacar primeiro saneamento de dados, escalas e unidades.

Nao e recomendavel recriar a navegacao final antes do Batch 01 e Batch 02, porque isso apenas mudaria a forma da tela sem resolver o risco de unidade/escala e filtro global.

## Proximo Batch

BATCH 01 - Saneamento dos dados, escalas e unidades.

Entrega esperada no Batch 01:

- criar `market_indicator_metadata`;
- criar `market_data_quality_alerts`;
- criar funcao/rotina central `validate_indicator_value()`;
- cadastrar metadata inicial para BCB, CNI, World Bank, ANEEL, Aco Brasil e Comex;
- impedir publicacao de valores invalidos;
- preservar NULL como NULL;
- documentar regras iniciais de sanity.
