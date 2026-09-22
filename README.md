# ABR Intelligence

ABR Intelligence e uma plataforma de inteligencia comercial, operacional e de mercado para o Grupo ABR. O objetivo e transformar dados internos, planilhas operacionais, sinais de mercado e capturas autorizadas do Aster em diagnostico, previsao e acao.

## Para Que Serve

- Consolidar pedidos, clientes, estoque, materiais, margens e indicadores de mercado.
- Importar planilhas XLSX grandes com rastreabilidade, checkpoints e idempotencia.
- Manter uma camada de staging auditavel antes de promover dados para tabelas finais.
- Indicar claramente se os dashboards usam base real, base vazia ou dados de demonstracao.
- Oferecer fallback operacional para o Aster quando nao houver API oficial disponivel.

Leia tambem [docs/program-overview.md](docs/program-overview.md) para a explicacao funcional do produto e dos modulos esperados.

## Arquitetura

A organizacao atual esta documentada em [docs/architecture.md](docs/architecture.md).

```text
backend/       Coletor Python, processamento local e navegacao Aster com Playwright.
frontend/      Componentes React e servicos usados pelo app principal.
supabase/      Edge Functions e migrations SQL.
extension/     Extensao Chrome para captura assistida do Aster.
tools/         Scripts locais de inspecao e manutencao.
docs/          Documentacao, diagnosticos e evidencias.
data/          Entradas operacionais locais, nao versionadas.
archive/       Pacotes recebidos/exportados, nao versionados.
```

## Workflows

Os fluxos operacionais estao detalhados em [docs/workflows.md](docs/workflows.md):

- Upload e processamento de XLSX.
- Promocao da staging para a base real.
- Captura assistida do Aster.
- Validacao da origem dos dados nos dashboards.
- Retomada de processamento por checkpoint.

## Testes

O relatorio da ultima depuracao esta em [docs/test-report.md](docs/test-report.md).

Smoke test local:

```powershell
.\.venv\Scripts\python.exe tools\smoke_test.py --json
```

## Ingestao Aster

O passo a passo para configurar a ingestao do coletor Python/extensao Aster esta em [docs/ingestion-setup.md](docs/ingestion-setup.md).

O catalogo das fontes/relatorios Aster por area esta em [docs/aster-data-sources.md](docs/aster-data-sources.md).

A matriz de treinamento do robo Aster fica em [docs/aster-training-matrix.md](docs/aster-training-matrix.md).

O workflow prioritario atual do Aster fica em [docs/aster-priority-workflow.md](docs/aster-priority-workflow.md).

## Backend Python

A camada Python proposta fica em [backend/](backend/README.md) e usa `pandas`, `openpyxl`, `Playwright`, `httpx` e bibliotecas de configuracao. Ela serve para processamento local/worker e para navegar no Aster de modo autorizado quando nao houver API oficial.

Dependencias:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## API de Extracao

A API FastAPI fica em [backend/api](backend/api) e esta documentada em [docs/api.md](docs/api.md).

Rodar local:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Documentacao interativa:

```text
http://127.0.0.1:8000/docs
```

Blueprint do Render:

```text
render.yaml
```

## Seguranca

Credenciais nao devem ser gravadas no repositorio. Use [.env.example](.env.example) como referencia e configure secrets no ambiente correto do Supabase ou no backend/coletor.

As planilhas em `data/input/` e o ZIP em `archive/` sao artefatos operacionais locais. Eles foram mantidos organizados para analise, mas nao devem ser publicados como codigo-fonte.

## Estado Atual

Este workspace contem um recorte organizado do projeto, com foco no pipeline de dados e na extensao Aster. Ele nao contem um projeto frontend completo com `package.json`, `src/` completo e todas as dependencias; os arquivos React aqui representam modulos extraidos que devem ser reintegrados ao app principal.

Se o VS Code mostrar muitos problemas no painel **Problems**, consulte [docs/editor-problems.md](docs/editor-problems.md). A maior parte dos avisos neste recorte vem de dependencias ausentes do app completo, nao de erros reais nos fluxos documentados.
