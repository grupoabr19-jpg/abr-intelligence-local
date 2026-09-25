# Batches 11 a 20 - Atendimento

Data: 2026-09-25

## Batch 11 - Eventos Kommo

Implementado:

- coleta opcional de eventos por `/api/v4/events`;
- variavel `KOMMO_COLLECT_EVENTS`;
- persistencia em `raw_kommo_events`;
- auditoria de status/erro de eventos em `atendimento_ingestion_runs`.

Observacao: a API oficial do Kommo documenta o endpoint `GET /api/v4/events` com filtros por `created_at`, `entity`, `entity_id`, `type` e paginacao.

## Batch 12 - Agregados de atendimento

Implementado:

- `atendimento_agregado_diario`
- `atendimento_agregado_colaborador`
- `atendimento_agregado_regiao`

Esses agregados sao recalculados por `tools/refresh_atendimento_facts.py`.

## Batch 13 - Eventos vinculados a fatos

Implementado:

- `atendimento_evento_resposta`
- cruzamento de `raw_kommo_events` com `fato_atendimento_lead`.

Limitacao atual: eventos RAW podem existir sem lead correspondente no fato ativo; nesse caso ficam preservados no RAW e nao entram como evento vinculado.

## Batch 14 - API com agregados

Implementado no payload `attendance_summary`:

- `daily`
- `origins`
- `event_types`
- `event_stats`

## Batch 15 - Dashboard operacional

Implementado:

- Evolucao diaria de leads na Visao Geral.
- Aba Canais com origem dos leads.
- Aba Ocorrencias com tipos de eventos Kommo.

## Batch 16 - Qualidade ampliada

Mantido:

- `atendimento_data_quality`
- leads sem SLA calculavel;
- leads sem colaborador;
- leads excluidos por regra operacional.

## Batch 17 - Operacao de coleta

Com eventos desligados:

```powershell
.\.venv\Scripts\python.exe tools\collect_kommo_attendance.py --date-from 2026-01-01 --date-to 2026-09-25
```

Com eventos ligados:

```powershell
$env:KOMMO_COLLECT_EVENTS='true'
.\.venv\Scripts\python.exe tools\collect_kommo_attendance.py --date-from 2026-01-01 --date-to 2026-09-25
```

Depois da coleta:

```powershell
.\.venv\Scripts\python.exe tools\refresh_atendimento_facts.py
```

## Batch 18 - Render/Cron

Variavel nova:

- `KOMMO_COLLECT_EVENTS=false`

Recomendacao operacional:

- manter `false` se a carga de eventos ficar pesada;
- ligar `true` apenas no cron noturno ou em carga incremental menor.

## Batch 19 - Validacao

Validacoes esperadas:

- `py_compile` dos scripts;
- `unittest` de regras de atendimento;
- `npm run build`;
- refresh com retorno de agregados.

## Batch 20 - Fechamento

Estado apos este lote:

- Atendimento tem RAW, dimensoes, fatos, agregados e eventos opcionais.
- Dashboard mostra origem/canais e eventos sem depender de grafico clonado.
- Eventos sem correspondencia em fatos ficam preservados como RAW, sem forcar cruzamento falso.

Proximos passos recomendados:

- buscar eventos incrementalmente por `created_at` da ultima carga;
- classificar quais `event_type` representam primeira mensagem e primeira resposta humana;
- recalcular SLA por eventos reais quando essa classificacao estiver validada;
- criar alerta operacional quando `linked_events` for muito menor que `raw_events`.
