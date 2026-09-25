# Batch 01 - Ingestao RAW Kommo

Data: 2026-09-25

## Objetivo

Criar a primeira camada RAW do modulo Atendimento para que os dados do Kommo deixem de depender apenas de `public.staging_dados`.

Este batch preserva o dashboard atual: a staging continua sendo alimentada com `entidade = 'atendimento_kommo'`, enquanto as novas tabelas RAW passam a guardar as entidades originais do Kommo.

## Arquitetura implementada

O fluxo do Kommo passou a ser:

1. `tools/collect_kommo_attendance.py` consulta a API Kommo.
2. O coletor busca usuarios, funis, etapas, tarefas abertas e leads.
3. O payload bruto e gravado nas tabelas RAW.
4. O lead normalizado continua sendo gravado em `public.staging_dados`.
5. `backend/api/data.py::attendance_summary()` continua lendo a staging, mantendo compatibilidade com o dashboard.

## Tabelas criadas

Migracao: `supabase/migrations/20260925133000_atendimento_kommo_raw_layer.sql`

Tabelas:

- `public.atendimento_ingestion_runs`
- `public.raw_kommo_users`
- `public.raw_kommo_pipelines`
- `public.raw_kommo_statuses`
- `public.raw_kommo_leads`
- `public.raw_kommo_tasks`
- `public.raw_kommo_events`

Todas as tabelas foram criadas com RLS habilitado e policy de leitura para `authenticated`.

## Idempotencia

As tabelas RAW trabalham com versoes por hash:

- cada entidade tem um identificador Kommo;
- cada payload gera `raw_hash`;
- existe uma constraint unica por identificador + hash;
- se o payload atual ja esta ativo com o mesmo hash, a carga ignora;
- se o payload mudou, a versao ativa anterior e desativada e a nova versao fica ativa.

A staging manteve o comportamento anterior:

- `source_system = 'KOMMO_API'`
- `entidade = 'atendimento_kommo'`
- `source_id = 'kommo_lead:<id>'`
- `hash_registro` evita duplicacao da versao ativa.

## Validacao executada

Comando de migracao:

```powershell
.\.venv\Scripts\python.exe tools\apply_migrations.py
```

Resultado:

```text
apply 20260925133000_atendimento_kommo_raw_layer.sql
migrations_ok
```

Comando de carga pequena:

```powershell
.\.venv\Scripts\python.exe tools\collect_kommo_attendance.py --date-from 2026-01-01 --date-to 2026-09-25 --page-limit 5 --max-pages 1
```

Primeira execucao:

```json
{
  "rows_found": 5,
  "users_found": 5,
  "pipelines_found": 5,
  "open_tasks_found": 3,
  "inserted": 5,
  "skipped": 0,
  "raw_inserted": 58,
  "raw_skipped": 0
}
```

Segunda execucao com os mesmos filtros:

```json
{
  "rows_found": 5,
  "users_found": 5,
  "pipelines_found": 5,
  "open_tasks_found": 3,
  "inserted": 0,
  "skipped": 5,
  "raw_inserted": 0,
  "raw_skipped": 58
}
```

Conclusao: a carga pequena confirmou idempotencia para RAW e staging.

Contagens consultadas apos a validacao:

- `atendimento_ingestion_runs`: 2 execucoes com status `sucesso`.
- `raw_kommo_users`: 5 registros totais, 5 ativos.
- `raw_kommo_pipelines`: 5 registros totais, 5 ativos.
- `raw_kommo_statuses`: 38 registros totais, 38 ativos.
- `raw_kommo_leads`: 5 registros totais, 5 ativos.
- `raw_kommo_tasks`: 5 registros totais, 5 ativos.
- `raw_kommo_events`: 0 registros totais, 0 ativos.

## Limites conhecidos

- `raw_kommo_events` foi criada para a proxima etapa, mas ainda nao e populada pelo coletor.
- O dashboard ainda nao le as tabelas RAW diretamente.
- Os calculos seguem em `attendance_summary()` lendo `staging_dados`.
- A regra de regiao/polo ainda tem fallback hardcoded em `backend/api/data.py`.
- A dimensao `dim_regiao_varejo` ainda precisa evoluir para cobrir Atacado no banco.
- Nao foi criada rotina agendada neste batch.

## Proximo batch recomendado

Batch 02 deve criar as dimensoes operacionais e tirar regras fixas do codigo:

- `dim_atendimento_colaborador`
- `dim_atendimento_regiao_polo`
- `dim_kommo_pipeline`
- `dim_kommo_status`
- `dim_atendimento_origem`
- carga das dimensoes a partir das RAW;
- ajuste da regra de Atacado em banco;
- testes de consistencia entre RAW e dimensoes.
