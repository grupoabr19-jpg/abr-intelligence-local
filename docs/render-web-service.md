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
ABR_ENABLE_WEB_AUTO_REFRESH=true
ABR_ENABLE_WEB_REFRESH_JOBS=true
DATABASE_NEON_URL=
DATABASE_NEON_URL_POOLER=
DATABASE_MARKET_URL_POOLER=
DATABASE_MARKET_URL=
DATABASE_URL_POOLER=
DATABASE_URL=
SUPABASE_URL=
SUPABASE_SECRET_KEY=
ABR_INGEST_URL=https://<render-service>.onrender.com/v1/collector/ingest
ABR_COLLECTOR_KEY=
ABR_ASTER_FONTE_ID=
ABR_ASTER_ENTIDADE=aster_relatorio
ASTER_BASE_URL=https://aster.gruposps.com.br/Login/abr
ASTER_LOGIN_EMAIL=
ASTER_LOGIN_PASSWORD=
```

Nao precisa configurar `VITE_ABR_API_BASE_URL` nesse modo: o frontend usa a mesma origem do Web Service. Tambem nao configure chaves `VITE_*` para autenticar o dashboard; o login usa cookie HttpOnly emitido pelo backend.

## Atualizacao diaria sem Render Cron

Em conta free, o Web Service pode disparar a atualizacao automaticamente no primeiro acesso do dia. O backend verifica se as fontes obrigatorias ja foram atualizadas hoje; se nao foram, inicia uma carga D-1 em segundo plano. Depois dessa primeira tentativa, novas aberturas no mesmo dia nao repetem a coleta; o botao do cabecalho continua disponivel para comando manual.

Mantenha no Web Service:

```env
ABR_ENABLE_WEB_AUTO_REFRESH=true
ABR_ENABLE_WEB_REFRESH_JOBS=true
```

Para execucoes longas fora do Web Service, o orquestrador usa heartbeat por etapa e considera um job stale somente depois de:

```env
ABR_REFRESH_STALE_MINUTES=240
```

No modo automatico, a extracao operacional busca somente o dia anterior para evitar recarregar o ano inteiro no Aster todos os dias. A ordem da esteira e:

1. extrair os relatorios do Aster;
2. gerar o compilado da staging Aster e subir no Drive;
3. recalcular fatos/cache do dashboard;
4. ler planilhas brutas do Drive;
5. atualizar Kommo/CRM;
6. atualizar Mercado/Neon.

Se algum relatorio Aster falhar ou se o compilado nao subir no Drive, as etapas de fatos/cache/planilhas sao puladas para evitar dashboard com base incompleta.

Com isso:

- o startup aguarda alguns segundos antes de checar a carga;
- a primeira abertura do dia dispara a rotina apenas uma vez;
- cada grupo de fontes so roda se o banco correspondente estiver acessivel;
- o botao de atualizar executa a mesma rotina por comando manual.

Comando recomendado para Cron/Worker:

```bash
python tools/run_dashboard_refresh.py --mode auto
```

Para execucao manual com periodo especifico:

```bash
python tools/run_dashboard_refresh.py --mode manual --force --date-from 2026-01-01 --date-to 2026-09-30
```

## Cron opcional

Se a conta nao aceitar Blueprint, o cron tambem precisa ser substituido por uma alternativa externa, por exemplo:

- Render Cron/Worker criado manualmente em conta paga rodando `python tools/run_dashboard_refresh.py --mode auto`.
- GitHub Actions agendado executando o mesmo comando com as variaveis de ambiente.
- Cron externo chamando uma rotina propria fora do Web Service.

## Alternativa externa sem Render Cron

Para conta Render free, mantenha o Web Service apenas servindo o dashboard e use o GitHub Actions para rodar o robo de dados diariamente. O workflow fica em:

```text
.github/workflows/daily-dashboard-refresh.yml
```

Ele roda todos os dias as 08:30 UTC, equivalente a 05:30 em Sao Paulo, e tambem pode ser acionado manualmente em `Actions > Daily dashboard refresh > Run workflow`.

Secrets necessarios no GitHub:

```text
DATABASE_NEON_URL
DATABASE_NEON_URL_POOLER
DATABASE_MARKET_URL_POOLER
DATABASE_MARKET_URL
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

Se optar por GitHub Actions ou outro worker externo, desabilite o disparo no Web Service para evitar duas cargas simultaneas:

```env
ABR_ENABLE_WEB_AUTO_REFRESH=false
ABR_ENABLE_WEB_REFRESH_JOBS=false
```
