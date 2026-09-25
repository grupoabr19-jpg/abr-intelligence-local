# Batch 00 - Arquitetura Atual do Modulo Atendimento

Data da auditoria: 2026-09-25

## 1. Arquitetura encontrada

O projeto atual e uma aplicacao full-stack leve, organizada em tres camadas principais:

- Frontend: React + Vite em `frontend/src`, com dashboard em pagina unica no arquivo `frontend/src/App.tsx`.
- Backend: FastAPI em `backend/api`, exposto pelo `app.py` na raiz para deploy em Render.
- Banco: Supabase/Postgres, com migracoes em `supabase/migrations` e carga por scripts Python.

O backend centraliza as rotas em `backend/api/main.py`. As rotas ativas mais importantes para o Atendimento sao:

- `GET /health`: saude do servico.
- `POST /v1/auth/dashboard-login`: login do dashboard por senha.
- `POST /v1/auth/dashboard-logout`: encerra sessao.
- `GET /v1/auth/dashboard-session`: valida sessao.
- `GET /v1/dashboard/internal`: entrega o payload consolidado usado pelo frontend.
- `GET /v1/aster/reports`: lista relatorios mapeados do Aster.
- `POST /v1/aster/extractions`: dispara uma extracao Aster em job local.
- `GET /v1/jobs` e `GET /v1/jobs/{job_id}`: consulta jobs em memoria.
- `GET /v1/sales/regions-summary`: resumo comercial por regiao.

A autenticacao fica em `backend/api/security.py`:

- API tecnica: `ABR_API_KEY` via header `x-api-key`.
- Dashboard humano: senha `ABR_DASHBOARD_PASSWORD`.
- Sessao do dashboard: cookie `abr_dashboard_session` e header `x-dashboard-session`.
- Chave de leitura opcional: `ABR_DASHBOARD_READ_KEY`.

Os modelos de entrada/saida da API ficam em `backend/api/models.py`. A configuracao do backend fica em `backend/api/config.py`, lendo `.env` por `pydantic-settings`.

## 2. Fluxo atual de dados

### Atendimento / Kommo

Fluxo encontrado:

1. `tools/collect_kommo_attendance.py` consulta diretamente a API Kommo.
2. O script busca usuarios, funis, etapas, tarefas e leads.
3. Cada lead e normalizado para um payload com campos como:
   - `ID do lead`
   - `Nome do lead`
   - `Criado em`
   - `Atualizado em`
   - `Fechado em`
   - `Situacao`
   - `Funil`
   - `Etapa`
   - `Status ID`
   - `Pipeline ID`
   - `Primeiro contato recebido`
   - `Primeira resposta humana`
   - `Espera em minutos`
   - `Valor`
   - `Proxima tarefa`
   - `Origem`
   - `Regiao`
   - `Segmento`
   - `Temperatura`
   - `Responsavel`
   - `Responsavel ID`
   - `Quem respondeu primeiro`
   - `Link Kommo`
   - `_kommo`
4. Os registros sao gravados em `public.staging_dados` com:
   - `source_system = 'KOMMO_API'`
   - `entidade = 'atendimento_kommo'`
   - `source_id = 'kommo_lead:<id>'`
   - `ativo = true` apenas para a versao atual do lead.
5. `backend/api/data.py::attendance_summary()` le os registros ativos da staging.
6. O resumo de atendimento e anexado ao payload de `GET /v1/dashboard/internal`.
7. O frontend consome `attendance_summary` em `frontend/src/api.ts` e renderiza no modulo Atendimento.

Hoje o Kommo nao possui camada propria de tabelas RAW, fato ou dimensao analitica. A `staging_dados` faz papel duplo: preservacao do payload e base operacional para calculo.

### Aster / ERP

Fluxo encontrado:

1. Os relatorios conhecidos ficam em `backend/aster_collector/report_registry.py`.
2. A configuracao Aster fica em `backend/aster_collector/settings.py`.
3. A API pode disparar extracoes via `POST /v1/aster/extractions`.
4. O job usa `backend/api/jobs.py`, mas o controle e em memoria.
5. O dado coletado e persistido em `public.staging_dados` com entidades como `aster_report_d0a4d301`.
6. `backend/api/data.py` calcula resumos comerciais a partir da staging.
7. O resumo comercial pode ser cacheado em `public.dashboard_sales_summary_cache` por `tools/refresh_dashboard_sales_cache.py`.

### Planilhas locais

Fluxo encontrado:

1. `backend/aster_collector/local_spreadsheets.py` inspeciona planilhas em `Planilhas/`.
2. A rota `POST /v1/spreadsheets/local/inspect` aciona a inspecao.
3. O resultado e salvo em `docs/evidence/local_spreadsheet_sources_summary.json` e `.md`.
4. Nao foi encontrada promocao completa e padronizada dessas planilhas para fatos/dimensoes do Atendimento.

### Mercado

Fluxo encontrado:

1. `tools/collect_market_sources.py` raspa paginas publicas configuradas por variaveis de ambiente.
2. A carga usa as tabelas `mercado_fontes`, `mercado_coletas`, `mercado_documentos` e `mercado_indicadores`.
3. Esse fluxo pertence ao modulo Mercado, nao ao Atendimento, mas ja serve como exemplo reutilizavel de catalogo/coleta/documentos.

## 3. Estrutura atual do modulo Atendimento

No frontend, o modulo Atendimento e definido dentro de `frontend/src/App.tsx`.

Abas encontradas:

- `Visao Geral`
- `Ranking`
- `SLA`
- `Clientes`
- `Ocorrencias`
- `Pedidos`
- `Entregas`
- `Reclamacoes`
- `Satisfacao`
- `Canais`
- `Equipe`

Estado atual:

- `Visao Geral`: implementada parcialmente com KPIs, resumo recebido do Kommo, campos pendentes, pipeline aberto e win rate por funil quando ha base granular.
- `Ranking`: implementado parcialmente com ranking por colaborador e ranking por regiao/polo.
- Demais abas: usam `UnavailableTab`, exibindo que faltam dados para cruzamentos.

A regra de regiao/polo do ranking esta implementada em duas camadas:

- Banco: `public.dim_regiao_varejo`, criada pela migracao `20260924214500_dim_regiao_varejo.sql`.
- Fallback em codigo: `VAREJO_REGION_FALLBACK` dentro de `backend/api/data.py`.

Observacao importante: o fallback em codigo ja inclui colaboradores de Atacado, mas a migracao `dim_regiao_varejo` tem check constraint de `funcao` sem `ATACADO`. Portanto, a dimensao no banco ainda nao representa integralmente a regra operacional atual.

## 4. Tabelas existentes

Tabelas centrais encontradas nas migracoes:

- `public.clientes`
- `public.materiais`
- `public.depositos`
- `public.pedidos_venda`
- `public.itens_pedido`
- `public.estoque`
- `public.fornecedores`
- `public.precos_mercado`
- `public.fontes_dados`
- `public.mapeamento_campos`
- `public.historico_importacoes`
- `public.importacoes`
- `public.staging_dados`
- `public.indicadores_economicos`
- `public.dashboard_sales_summary_cache`
- `public.mercado_fontes`
- `public.mercado_coletas`
- `public.mercado_documentos`
- `public.mercado_indicadores`
- `public.dim_regiao_varejo`
- `public.abr_migrations_applied`

Tabelas/views/funcoes endurecidas por seguranca:

- Views: `reconciliacao_faturamento`, `pendencias_cruzamento`, `anulados_cruzamento`, `reconciliation_summary`, `meta_ativa`, `realizado_ativo`.
- Funcao: `public.rls_auto_enable()`.

Nao foram encontradas, ate este batch, tabelas especificas como:

- `raw_kommo_leads`
- `raw_kommo_tasks`
- `raw_kommo_events`
- `raw_aster_*`
- `fato_atendimento_lead`
- `fato_atendimento_evento`
- `fato_sla_atendimento`
- `dim_colaborador`
- `dim_funil_kommo`
- `dim_etapa_kommo`
- `dim_canal_atendimento`

## 5. Pontos reutilizaveis

Componentes e padroes que devem ser reaproveitados nos proximos batches:

- Conexao com banco e leitura de `.env`: `tools/apply_migrations.py::connect_database()` e `load_env()`.
- Staging auditavel: `public.staging_dados` com `payload_original`, `dados_transformados`, `hash_registro`, `sync_id` e `ativo`.
- Idempotencia de carga: padrao usado em `tools/collect_kommo_attendance.py` com hash do payload e desativacao da versao anterior.
- Catalogo de fonte: `public.fontes_dados` e `public.historico_importacoes`.
- Resumo de Atendimento: `backend/api/data.py::attendance_summary()`.
- Normalizacao de textos, datas e numeros do Atendimento: funcoes auxiliares em `backend/api/data.py`.
- Regra de regiao/polo: `public.dim_regiao_varejo` e fallback atual.
- API consolidada: `GET /v1/dashboard/internal`.
- Tipagem frontend: `frontend/src/api.ts::DashboardSummary`.
- Componentes visuais reaproveitaveis: `Kpi`, `Panel`, `ChartFrame`, `UnavailableTab`, tabelas e graficos Recharts em `frontend/src/App.tsx`.
- Cache comercial: `public.dashboard_sales_summary_cache` e `tools/refresh_dashboard_sales_cache.py`.
- Jobs locais: `backend/api/jobs.py`, util como padrao inicial, mas insuficiente para operacao duravel.
- Registro de relatorios Aster: `backend/aster_collector/report_registry.py`.
- Scraping/carga de mercado: `tools/collect_market_sources.py`, util como referencia para fontes externas.

## 6. Riscos

Riscos tecnicos e funcionais identificados:

- A camada de Atendimento depende de `staging_dados` como fonte analitica direta. Isso dificulta governanca, versionamento de schema, performance e auditoria por tipo de evento.
- Nao ha RAW dedicado para Kommo. O `_kommo` fica embutido no JSON do lead, mas nao existe historico relacional separado de leads, tasks, eventos, usuarios, pipelines e status.
- O calculo de SLA depende de campos customizados ou inferencias. Se `Primeiro contato recebido`, `Primeira resposta humana` ou `Espera em minutos` nao estiverem preenchidos corretamente, o indicador fica incompleto.
- O primeiro respondente pode nao refletir a verdade operacional completa se vier apenas de campos do lead ou `updated_by`; a fonte correta pode exigir eventos/notas/mensagens.
- O ranking de regiao/polo usa cadastro fixo, mas parte da regra ainda esta hardcoded em `backend/api/data.py`.
- A tabela `dim_regiao_varejo` ainda nao aceita `ATACADO`, apesar do fallback em codigo ja tratar Wilson, Larissa e Julio como Atacado.
- O controle de jobs e em memoria. Em Render, reinicio do processo perde historico de jobs.
- O dashboard mistura varios dominios dentro de um unico payload grande em `/v1/dashboard/internal`.
- O cache comercial tem fallback de periodo e pode retornar base de data final anterior quando a data solicitada ainda nao esta cacheada.
- Algumas migracoes e arquivos mostram sinais de encoding antigo/mojibake. Isso aumenta risco de comparacao textual errada em nomes com acento.
- As politicas RLS atuais parecem amplas para usuario autenticado nas tabelas centrais; precisa revisao quando houver dados sensiveis por colaborador ou cliente.
- Nao ha scheduler padronizado no repositorio para cargas recorrentes Kommo/Aster/Mercado.
- Nao ha testes automatizados especificos para os calculos de Atendimento.

## 7. Mudancas necessarias

Mudancas necessarias antes de expandir graficos e regras de Atendimento:

1. Criar camada RAW dedicada para Kommo:
   - leads
   - tasks
   - pipelines
   - statuses/etapas
   - users
   - events/notas/mensagens, se disponiveis pela API

2. Criar dimensoes operacionais:
   - colaborador
   - funcao
   - regiao/polo
   - funil
   - etapa/status
   - canal/origem
   - data/calendario

3. Corrigir a dimensao de regiao/polo:
   - remover hardcode gradualmente do backend.
   - incluir `ATACADO` no banco.
   - manter a regra explicita de que Ranking usa praca/polo do colaborador, nao cidade do lead.

4. Criar fatos de Atendimento:
   - fato de lead
   - fato de evento/resposta
   - fato de SLA
   - fato de pipeline aberto
   - fato de conversao/perda

5. Separar indicadores de apresentacao:
   - backend deve devolver metricas ja calculadas com nomes consistentes.
   - frontend deve apenas renderizar, formatar e filtrar.

6. Criar testes de calculo:
   - win rate por colaborador e por regiao.
   - SLA por colaborador e por regiao.
   - pipeline aberto e valor pipeline.
   - cobertura de follow-up.
   - exclusoes de Liderancas e Comunicacao Interna.

7. Criar trilha de auditoria:
   - quantidade lida por fonte.
   - quantidade inserida/atualizada.
   - quantidade descartada.
   - motivo de descarte.
   - data da ultima carga.

8. Definir execucao recorrente:
   - Render Cron, worker, ou comando operacional padronizado.
   - logs persistentes em tabela, nao apenas stdout.

## 8. Plano para Batch 01

Objetivo recomendado para o Batch 01: criar a camada RAW e a base minima de governanca da ingestao do Atendimento, sem alterar graficos.

Escopo recomendado:

1. Criar migracao SQL para tabelas RAW Kommo:
   - `raw_kommo_users`
   - `raw_kommo_pipelines`
   - `raw_kommo_statuses`
   - `raw_kommo_leads`
   - `raw_kommo_tasks`
   - `raw_kommo_events` ou tabela equivalente, se a API disponivel permitir.

2. Criar tabela de execucao de cargas:
   - `atendimento_ingestion_runs`
   - status, inicio, fim, fonte, paginas, lidos, inseridos, atualizados, erros.

3. Ajustar `tools/collect_kommo_attendance.py` para gravar RAW sem remover a compatibilidade atual com `staging_dados`.

4. Validar idempotencia:
   - mesma carga nao duplica registros.
   - alteracao no Kommo gera nova versao ou atualizacao controlada.

5. Criar comandos de verificacao:
   - contagem por tabela RAW.
   - ultima carga.
   - amostra sem expor token ou segredo.

6. Documentar em `docs/atendimento/01_ingestao_raw.md`.

Critério de aceite do Batch 01:

- RAW Kommo criado e populavel.
- Nenhuma regra de ranking alterada.
- Nenhum grafico novo.
- Compatibilidade mantida com o dashboard atual.
- Teste/validacao mostrando contagens e idempotencia.
