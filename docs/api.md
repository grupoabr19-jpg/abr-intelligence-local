# ABR Intelligence Data API

API FastAPI para disparar extracoes autorizadas do Aster e consultar dados tratados.

## Rodar Local

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Documentacao interativa:

```text
http://127.0.0.1:8000/docs
```

OpenAPI JSON:

```text
http://127.0.0.1:8000/openapi.json
```

## Autenticacao

Se `ABR_API_KEY` estiver preenchida no ambiente, envie:

```http
x-api-key: <ABR_API_KEY>
```

Se `ABR_API_KEY` estiver vazia, a autenticacao fica desabilitada para desenvolvimento local.

## Endpoints

### Health

```http
GET /health
```

Retorna:

```json
{"status":"ok","service":"abr-data-api"}
```

### Relatorios Aster Treinados

```http
GET /v1/aster/reports
```

Lista o registro operacional de relatorios Aster, incluindo status de automacao.

### Disparar Extracao Aster

```http
POST /v1/aster/extractions
content-type: application/json
```

Body:

```json
{
  "query_id": "D0A4D301",
  "date_from": "2026-09-01",
  "date_to": "2026-09-30",
  "timeout_seconds": 600
}
```

Resposta:

```json
{
  "job_id": "...",
  "status": "queued",
  "query_id": "D0A4D301",
  "status_url": "/v1/jobs/..."
}
```

### Consultar Job

```http
GET /v1/jobs/{job_id}
```

Status possiveis:

```text
queued | running | succeeded | failed
```

### Listar Jobs Recentes

```http
GET /v1/jobs
```

Observacao: a fila atual e em memoria. Em producao, se o servico reiniciar, o historico dos jobs em memoria e perdido, mas as cargas concluidas continuam no Supabase.

### Vendas por Canal e Regiao

```http
GET /v1/sales/regions-summary
```

Retorna vendas classificadas por:

- `varejo`
- `atacado`
- `indefinido`

Com regiao de varejo ou DDD do atacado quando o mapa consegue classificar.

## Deploy no Render

O arquivo [render.yaml](../render.yaml) cria um Web Service Docker.

```text
runtime: docker
dockerfilePath: ./Dockerfile
healthCheckPath: /health
```

O [Dockerfile](../Dockerfile) usa a imagem oficial do Playwright para Python, ja com Chromium e dependencias de sistema.

Configure os secrets no Render, sem versionar valores reais:

```env
ABR_API_KEY=
DATABASE_URL_POOLER=
SUPABASE_URL=
SUPABASE_SECRET_KEY=
ABR_INGEST_URL=
ABR_COLLECTOR_KEY=
ABR_ASTER_FONTE_ID=
ASTER_LOGIN_EMAIL=
ASTER_LOGIN_PASSWORD=
```

Variaveis com valor fixo no Blueprint:

```env
HEADLESS=true
ABR_ASTER_ENTIDADE=aster_relatorio
ASTER_BASE_URL=https://aster.gruposps.com.br/Login/abr
```

Depois do deploy, confira:

```text
https://<servico-render>.onrender.com/health
https://<servico-render>.onrender.com/docs
```
