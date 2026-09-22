# Relatorio de Depuracao e Testes

Data: 2026-09-22

## Ambiente

- Python: 3.12.10
- Ambiente virtual: `.venv`
- Dependencias instaladas de `requirements.txt`
- Chromium Playwright instalado

## Testes Executados

| Area | Resultado | Observacao |
|---|---:|---|
| Sintaxe Python (`py_compile`) | OK | Backend Python e scripts principais compilam. |
| Dependencias Python | OK | `pandas`, `openpyxl`, `pyarrow`, `playwright`, `httpx`, `pydantic`, `psycopg` e `tenacity` instalados. |
| Manifest da extensao | OK | `extension/aster-capture/manifest.json` e JSON valido. |
| XLSX Gestao | OK | Aba `Gestao da ProdV6`, 44.922 linhas de dados, 59 colunas, 5 chunks de 10.000. |
| XLSX Margem | OK | Aba `BD_Meta`, 54.463 linhas de dados, 47 colunas, 6 chunks de 10.000. |
| Cabecalhos vazios Margem | Corrigido | Colunas vazias viram `__empty_46` e `__empty_47`. |
| Supabase probe | OK | Scripts priorizam pooler IPv4; `us-west-2:6543` conecta. |
| Migrations Supabase | OK | 5 migrations aplicadas; 15 tabelas publicas criadas/validadas. |
| Edge Function `abr-collector-ingest` | OK | Publicada com `verify_jwt=false` e autenticacao propria por `x-collector-key`. |
| Smoke ingestao Edge | OK | Retornou `sucesso=true`, gravou staging/historico e o registro de teste foi removido. |
| Seeds de fontes | OK | Fonte Aster, Aco Brasil, Worldsteel, Fastmarkets e Upload Manual criadas. |
| Playwright Aster | OK parcial | Chromium abre o portal; a sessao operacional depende de login assistido/credenciais reais. |
| Captura viva Aster | OK | Sessao viva capturou `GlobalContext`, menu e ReportQuery `D0A4D301` sem expor tokens. |
| Catalogo Aster | OK | 13 relatorios no menu; `ABR - Analise de Vendas por Item` parametrizado. |
| Captura `/execute` Aster | OK | POST `/execute` 2xx capturado; retorno com 3.865 linhas e 60 colunas. |
| Ingestao Aster staging | OK parcial | Amostra salva de 200 linhas enviada; 198 registros unicos ficaram em staging por idempotencia/hash. |
| Ingestao Aster automatica | OK | `D0A4D301` executado sem intervencao: datas preenchidas, `Confirmar` clicado, 154 linhas capturadas e historico `154/154`. |
| Resumo Comercial Aster | OK | `0F75E84D` executado sem intervencao: 16 linhas capturadas e historico `16/16`. |
| Segmentacao de Lead Aster | OK | `027051BD` executado/ingerido: 9.568 linhas e historico `9568/9568`. |
| Ultimo preco de venda Aster | OK | `CAF55C1D` executado/ingerido: 50 linhas e historico `50/50`. |
| Financeiro Aster | Em treino | `37D9E431` preenche PN real e datas, mas PN/período testado voltou sem `body.data`. |
| Estoque Aster | Bloqueado | `804C04C1` retornou `PageNotAuthorized` no perfil atual. |
| Acumulacao de lotes Edge | OK | Teste controlado enviou 2+3 linhas no mesmo `sync_id`; historico ficou `5/5` e dados de teste foram removidos. |
| Contratos dos relatorios Aster | OK | 13 relatorios varridos e classificados por area em `docs/aster-data-sources.md`. |

## Correcoes Aplicadas

1. `.venv` e dependencias Python preparadas.
2. Chromium do Playwright instalado.
3. Pipeline XLSX ajustado para planilhas grandes e cabecalhos vazios.
4. Coletor Aster preparado com login assistido e captura de sessao local.
5. Migration inicial Supabase tornou-se autossuficiente para banco limpo.
6. Tabela `importacoes`, RLS e indices de idempotencia foram alinhados com frontend e Edge Functions.
7. Scripts Supabase ajustados para priorizar `DATABASE_URL_POOLER`/pooler IPv4 e evitar tentativa direta IPv6.
8. Edge Function `abr-collector-ingest` publicada no projeto Supabase e validada com payload de smoke.
9. Captura viva do Aster gerou catalogo de relatorios e contrato inicial de ReportQuery.
10. Captura de `/execute` ajustada para aguardar resposta 2xx e permitir nova tentativa com periodo menor.
11. Ingestor de evidencia criado e validado contra a Edge Function.
12. Ingestor vivo em memoria criado para enviar todas as linhas sem salvar dataset bruto.
13. Varredura dos 13 relatorios Aster criada e documentada por area de negocio.
14. Registro operacional de relatorios criado em `backend/aster_collector/report_registry.py`.
15. Executor vivo passou a preencher formularios por configuracao de relatorio e clicar automaticamente em `Confirmar`.
16. Edge Function corrigida para acumular historico quando uma carga chega em varios lotes.
17. Matriz de treinamento criada em `docs/aster-training-matrix.md`.
18. Amostras reais de clientes, familias e itens extraidas de `D0A4D301` para treinar relatorios dependentes de parametros.

## Estado Supabase Atual

- Tabelas publicas: `abr_migrations_applied`, `clientes`, `depositos`, `estoque`, `fontes_dados`, `fornecedores`, `historico_importacoes`, `importacoes`, `indicadores_economicos`, `itens_pedido`, `mapeamento_campos`, `materiais`, `pedidos_venda`, `precos_mercado`, `staging_dados`.
- Fonte Aster: `a0000000-0000-4000-8000-000000000001`.
- `importacoes`: 0 registros.
- `staging_dados`: contem cargas Aster reais com idempotencia por hash de linha.

## Pendencias

- Rotacionar `ABR_COLLECTOR_KEY` para uma chave longa antes de uso produtivo.
- Iterar `Contas a Receber - PN` com lista maior de PNs ate encontrar contas com movimento.
- Resolver permissao/alternativa para relatorios de estoque bloqueados no perfil atual.
- Investigar fonte de producao; `Estrutura de Produto` precisa de item com BOM/estrutura cadastrada.
- Executar testes do frontend quando o app React completo estiver presente.
