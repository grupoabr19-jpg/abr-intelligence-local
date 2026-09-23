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

Nao precisa configurar `VITE_ABR_API_BASE_URL` nesse modo: o frontend usa a mesma origem do Web Service.

## Cron

Se a conta nao aceitar Blueprint, o cron tambem precisa ser substituido por uma alternativa externa, por exemplo:

- Render cron criado manualmente em conta paga.
- GitHub Actions agendado chamando `POST /v1/spreadsheets/local/inspect`.
- Cron externo chamando a API publicada com `x-api-key`.
