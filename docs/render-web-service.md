# Deploy Render Como Web Service

Contas gratuitas podem nao aceitar Blueprint. Nesse caso, crie apenas um **Web Service** manual no Render.

## Configuracao

- Repository: `https://github.com/grupoabr19-jpg/abr-intelligence-local`
- Runtime: `Docker`
- Branch: `master`
- Dockerfile path: `./Dockerfile`
- Health check path: `/health`

O Dockerfile builda o frontend React e copia `frontend/dist` para dentro do container Python. O FastAPI serve:

- API: `/v1/*`
- Health check: `/health`
- Frontend: `/`

## Variaveis

Configure no painel do Render, sem commitar valores reais:

```env
HEADLESS=true
ABR_API_KEY=
ABR_DASHBOARD_PASSWORD=
ABR_SESSION_SECRET=
ABR_ENABLE_WEB_AUTO_REFRESH=false
ABR_ENABLE_WEB_REFRESH_JOBS=false
DATABASE_URL_POOLER=
DATABASE_URL=
SUPABASE_URL=
SUPABASE_SECRET_KEY=
ABR_INGEST_URL=
ABR_COLLECTOR_KEY=
ABR_ASTER_FONTE_ID=
ABR_ASTER_ENTIDADE=aster_relatorio
ASTER_BASE_URL=https://aster.gruposps.com.br/Login/abr
ASTER_LOGIN_EMAIL=
ASTER_LOGIN_PASSWORD=
```

Nao precisa configurar `VITE_ABR_API_BASE_URL` nesse modo: o frontend usa a mesma origem do Web Service. Tambem nao configure chaves `VITE_*` para autenticar o dashboard; o login usa cookie HttpOnly emitido pelo backend.

## Memoria do Web Service

O Web Service deve servir somente API e frontend. Nao execute coleta Aster/Kommo/Drive/Mercado dentro dele em instancia pequena do Render.

Mantenha no Web Service:

```env
ABR_ENABLE_WEB_AUTO_REFRESH=false
ABR_ENABLE_WEB_REFRESH_JOBS=false
```

Com isso:

- o dashboard nao inicia coleta pesada no startup;
- abrir o dashboard nao dispara robo em segundo plano;
- o botao de atualizar nao executa subprocessos pesados no Web Service;
- a coleta deve rodar em Worker/Cron separado usando o mesmo Dockerfile.

Comando recomendado para Cron/Worker:

```bash
python tools/run_dashboard_refresh.py --mode auto
```

Para execucao manual com periodo especifico:

```bash
python tools/run_dashboard_refresh.py --mode manual --force --date-from 2026-01-01 --date-to 2026-09-30
```

## Cron

Se a conta nao aceitar Blueprint, o cron tambem precisa ser substituido por uma alternativa externa, por exemplo:

- Render Cron/Worker criado manualmente em conta paga rodando `python tools/run_dashboard_refresh.py --mode auto`.
- GitHub Actions agendado executando o mesmo comando com as variaveis de ambiente.
- Cron externo chamando uma rotina propria fora do Web Service.

## Alternativa sem Render Cron

Para conta Render free, mantenha o Web Service apenas servindo o dashboard e use o GitHub Actions para rodar o robo de dados diariamente. O workflow fica em:

```text
.github/workflows/daily-dashboard-refresh.yml
```

Ele roda todos os dias as 08:30 UTC, equivalente a 05:30 em Sao Paulo, e tambem pode ser acionado manualmente em `Actions > Daily dashboard refresh > Run workflow`.

Secrets necessarios no GitHub:

```text
DATABASE_URL_POOLER
DATABASE_URL
DATABASE_CRM_URL_POOLER
DATABASE_CRM_URL
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_SECRET_KEY
SUPABASE_CRM_URL
SUPABASE_CRM_PUBLISHABLE_KEY
SUPABASE_CRM_SECRET_KEY
ASTER_BASE_URL
ASTER_LOGIN_EMAIL
ASTER_LOGIN_PASSWORD
GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET
GOOGLE_OAUTH_REFRESH_TOKEN
ARCHIVE_GOOGLE_DRIVE_FOLDER_ID
DRIVE_SPREADSHEET_SOURCE_FOLDER_ID
KOMMO_API_BASE_URL
KOMMO_SUBDOMAIN
KOMMO_CLIENT_ID
KOMMO_CLIENT_SECRET
KOMMO_REDIRECT_URI
KOMMO_ACCESS_TOKEN
KOMMO_REFRESH_TOKEN
KOMMO_TOKEN_EXPIRES_AT
KOMMO_COLLECT_EVENTS
KOMMO_FIELD_ORIGIN
KOMMO_FIELD_REGION
KOMMO_FIELD_SEGMENT
KOMMO_FIELD_TEMPERATURE
```

No Render, deixe estes dois valores desabilitados para evitar estouro de memoria no Web Service:

```env
ABR_ENABLE_WEB_AUTO_REFRESH=false
ABR_ENABLE_WEB_REFRESH_JOBS=false
```
