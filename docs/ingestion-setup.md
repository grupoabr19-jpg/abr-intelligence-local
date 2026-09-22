# Ingestao Aster - Passo a Passo

Este checklist configura a entrada de dados do robo Python/extensao Aster para a staging do ABR Intelligence.

## Estado Atual Validado

- Banco Supabase acessivel pelo pooler IPv4 `us-west-2:6543`.
- Scripts locais priorizam `DATABASE_URL_POOLER` e nao tentam o host direto IPv6.
- Migrations aplicadas com sucesso em 2026-09-22.
- Edge Function `abr-collector-ingest` publicada e validada em 2026-09-22.
- Edge Function atualizada para acumular `registros_lidos`/`registros_inseridos` quando o mesmo `sync_id` chega em varios lotes.
- Smoke test de ingestao retornou `sucesso=true` e gravou em `staging_dados`/`historico_importacoes`.
- Captura viva do Aster validada: 13 relatorios no menu e ReportQuery `D0A4D301` mapeada.
- Execucao automatica do Aster validada para `D0A4D301`: o robo fez login, preencheu datas, clicou `Confirmar`, capturou `/execute` e ingeriu 154 linhas sem intervencao humana.
- Execucao automatica do Aster validada para `0F75E84D`: `Resumo Comercial` retornou 16 linhas e gravou historico `16/16`.
- Tabelas existentes: `fontes_dados`, `importacoes`, `staging_dados`, `historico_importacoes` e tabelas base de negocio.
- Smoke test local OK para a extensao e para as planilhas grandes.
- Fonte Aster seedada:

```text
a0000000-0000-4000-8000-000000000001 | ASTER ERP (SPS Group)
```

No `.env`, o `ABR_ASTER_FONTE_ID` ja pode ficar assim:

```env
ABR_ASTER_FONTE_ID=a0000000-0000-4000-8000-000000000001
```

Confira se esta preenchido localmente e tambem nos secrets da Edge Function:

```env
ABR_COLLECTOR_KEY=
```

## 1. Gerar a Chave do Coletor

No PowerShell:

```powershell
[guid]::NewGuid().ToString() + "-" + [guid]::NewGuid().ToString()
```

Copie o valor gerado para:

```env
ABR_COLLECTOR_KEY=<chave-gerada>
```

Use exatamente a mesma chave como secret da Edge Function no Supabase.

## 2. Configurar Secrets da Edge Function

No Dashboard do Supabase:

1. Abra o projeto `abr-intelligence`.
2. Va em **Edge Functions**.
3. Abra **Secrets**.
4. Cadastre:

```env
SUPABASE_URL=<url-do-projeto>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
ABR_COLLECTOR_KEY=<mesma-chave-do-env-local>
```

A funcao tambem aceita `SUPABASE_SECRET_KEY` como fallback, mas o nome padrao recomendado no Supabase e `SUPABASE_SERVICE_ROLE_KEY`.

## 3. Publicar ou Atualizar a Edge Function

Publique a pasta:

```text
supabase/functions/abr-collector-ingest
```

URL esperada:

```env
ABR_INGEST_URL=https://<project-ref>.supabase.co/functions/v1/abr-collector-ingest
```

Depois de publicar, valide:

```powershell
.\.venv\Scripts\python.exe tools\smoke_ingest_edge.py
```

Resultado esperado:

```json
{"sucesso":true,"recebidos":1}
```

## 4. Conferir a Fonte Aster Local

No `.env`:

```env
ABR_ASTER_FONTE_ID=a0000000-0000-4000-8000-000000000001
ABR_ASTER_ENTIDADE=aster_relatorio
```

## 5. Validar Banco e Pipeline Local

No `.env`, prefira:

```env
DATABASE_URL_POOLER=postgresql://postgres.<project-ref>:<senha>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

Se voce mantiver apenas `DATABASE_URL` com `db.<project-ref>.supabase.co`, os scripts usam essa URL apenas para extrair `project-ref` e senha, e entao tentam o pooler IPv4.

```powershell
.\.venv\Scripts\python.exe tools\supabase_probe.py
.\.venv\Scripts\python.exe tools\smoke_test.py
```

Resultados esperados:

- `public_table_count=15`
- `migrations_ok`, se rodar `tools\apply_migrations.py`
- `Gestao da ProdV6`: 44.922 linhas
- `BD_Meta`: 54.463 linhas

## 6. Login Assistido no Aster

Use este modo quando o portal exigir interacao humana ou validacao anti-automacao:

```powershell
.\.venv\Scripts\python.exe -m backend.aster_collector.cli manual-login-aster --timeout-seconds 600
```

Depois do login, a sessao fica em:

```text
.auth/aster_session.json
```

Esse arquivo e local e nao deve ser versionado.

## 7. Testar Descoberta Autenticada

Com a sessao salva:

```powershell
.\.venv\Scripts\python.exe tools\aster_authenticated_probe.py
```

Use o resultado para confirmar quais endpoints/relatorios do Aster respondem com a sua sessao real.

## 8. Capturar Catalogo de Relatorios Aster

Depois do login assistido, capture o relatorio aberto em uma sessao viva:

```powershell
.\.venv\Scripts\python.exe tools\aster_live_report_capture.py
.\.venv\Scripts\python.exe tools\build_aster_report_catalog.py
```

Saidas:

```text
docs/evidence/aster_live_report_capture.json
docs/evidence/aster_report_catalog.md
```

Estado atual:

- 13 relatorios encontrados no menu.
- `D0A4D301`: `ABR - Analise de Vendas por Item`.
- Parametros obrigatorios: `DATADE`, `DATAATE`.
- Contrato do POST `/execute` capturado.
- Execucao 2xx capturada com 3.865 linhas e 60 colunas.
- Amostra salva no arquivo de evidencia foi ingerida: 200 linhas enviadas, 198 registros unicos em staging.
- Primeira execucao usou janela 2017-01-01 ate 2026-09-30 e retornou `500 read ECONNRESET`, provavelmente por volume/timeout no Aster.

## 9. Capturar Execucao de Relatorio

Para aprender o formato dos dados baixaveis, rode:

```powershell
.\.venv\Scripts\python.exe tools\aster_live_execute_capture.py
```

Na janela do Aster:

1. Faca login se necessario.
2. Aguarde abrir `ABR - Analise de Vendas por Item`.
3. Preencha `Data de` e `Data ate` com uma janela curta, por exemplo 7 a 30 dias.
4. Clique no botao que realmente gera/executa o relatorio. Se a tela apenas recarregar os filtros, o POST `/execute` nao sera disparado.
5. Se o Aster retornar erro, tente novamente na mesma janela com periodo menor.
6. Aguarde o terminal encerrar quando ele capturar um `/execute` 2xx ou quando acabar o timeout.

Saidas esperadas:

```text
docs/evidence/aster_execute_capture_D0A4D301.json
docs/evidence/aster_execute_capture_D0A4D301.md
docs/evidence/aster_execute_summary_D0A4D301.md
```

Se terminar com `execute_event_count=0`, confira:

```text
docs/evidence/aster_execute_timeout_D0A4D301.png
```

Esse screenshot mostra onde a tela parou.

## 10. Ingerir Dados do Aster

Para ingerir a amostra ja salva no arquivo de evidencia:

```powershell
.\.venv\Scripts\python.exe tools\ingest_aster_execute_capture.py
```

Observacao: por seguranca, o arquivo de evidencia guarda apenas uma amostra dos dados. Na ultima captura, o Aster retornou 3.865 linhas, mas o arquivo salvo contem 200 linhas de preview.

Para capturar e ingerir todas as linhas em memoria, sem salvar o dataset bruto em disco:

```powershell
.\.venv\Scripts\python.exe tools\aster_live_execute_ingest.py
```

Esse fluxo abre o Aster, faz login com as credenciais do `.env` quando disponiveis, preenche os campos de data configurados para o relatorio, clica no botao de execucao e aguarda o POST `/execute` 2xx. Depois envia os dados para a Edge Function em lotes de ate 1.000 linhas e salva apenas um resumo em:

```text
docs/evidence/aster_live_ingest_summary_D0A4D301.json
```

Exemplo de janela curta para validar a automacao sem volume grande:

```powershell
.\.venv\Scripts\python.exe tools\aster_live_execute_ingest.py --query-id D0A4D301 --date-from 2026-09-01 --date-to 2026-09-01
```

Resultado validado:

```text
sync_id=ASTER-D0A4D301-1790100438
rows_captured=154
historico_importacoes=154/154
clicked=Confirmar
TIPO=null
_FILIAL=Todos
```

Para o `Resumo Comercial`:

```powershell
.\.venv\Scripts\python.exe tools\aster_live_execute_ingest.py --query-id 0F75E84D --date-from 2026-09-01 --date-to 2026-09-01
```

Resultado validado:

```text
sync_id=ASTER-0F75E84D-1790087326
rows_captured=16
historico_importacoes=16/16
clicked=Confirmar
```

Observacao: `staging_dados` e idempotente por hash do conteudo. Se uma linha ja entrou em uma carga anterior, uma nova execucao pode registrar `registros_lidos` no historico sem aumentar na mesma proporcao os registros unicos do staging.

No relatorio `D0A4D301`, o campo **Tipo** deve ficar vazio para representar todos. Forcar `Tipo=Todos` causa erro no Aster porque esse parametro espera valor numerico/interno. O campo **Filial** deve ser selecionado como `Todos` pelo dropdown.

## Observacoes de Seguranca

- Nao exponha `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_SECRET_KEY`, senha do banco ou `ABR_COLLECTOR_KEY`.
- O coletor deve trabalhar apenas em sessoes autorizadas.
- Se o Aster bloquear automacao, prefira API oficial, exportacao autorizada ou login assistido. Nao implemente evasao de controles do fornecedor.
