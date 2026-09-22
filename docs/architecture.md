# Arquitetura do ABR Intelligence

## Visao Geral

O sistema e organizado em quatro camadas:

1. **Interface e experiencia**: componentes React para login, Central de Dados e indicador de origem.
2. **Servico de dados no frontend**: funcoes TypeScript que conversam com Supabase, Storage, Edge Functions e RPCs.
3. **Backend Python**: processamento auxiliar com pandas/openpyxl e navegacao Aster com Playwright.
4. **Pipeline Supabase**: migrations, bucket privado `imports`, Edge Function `processar-importacao`, staging e promocao.
5. **Captura externa**: extensao Chrome para observar respostas JSON do portal Aster em uma sessao autorizada.

## Arvore de Arquivos

```text
.
|-- README.md
|-- .env.example
|-- .gitignore
|-- requirements.txt
|-- backend/
|   |-- README.md
|   `-- aster_collector/
|       |-- settings.py
|       |-- browser_capture.py
|       |-- xlsx_pipeline.py
|       `-- cli.py
|-- frontend/
|   |-- components/
|   |   |-- CentralDados.tsx
|   |   |-- DataOriginBadge.tsx
|   |   `-- Login.tsx
|   `-- services/
|       `-- centralDadosService.ts
|-- supabase/
|   |-- functions/
|   |   `-- processar-importacao/
|   |       `-- index.ts
|   `-- migrations/
|       |-- 20260918233630_central_dados_staging_catalog.sql
|       |-- 20260921140500_update_imports_bucket_size_limit.sql
|       |-- 20260921200000_persistir_aba_xlsx.sql
|       |-- 20260921203000_aster_staging_idempotencia.sql
|       `-- 20260921204500_aster_capture_metadata.sql
|-- extension/
|   `-- aster-capture/
|       |-- manifest.json
|       |-- background.js
|       |-- content.js
|       |-- page-hook.js
|       |-- popup.html
|       `-- popup.js
|-- tools/
|   `-- xlsx/
|       |-- inspect_xlsx_headers.py
|       |-- inspect_xlsx_structure.py
|       `-- patch_xlsx_sheet_selection.py
|-- docs/
|   |-- architecture.md
|   |-- workflows.md
|   |-- reference/
|   `-- evidence/
|-- data/
|   `-- input/
`-- archive/
```

## Responsabilidades

`frontend/components` contem telas e componentes do app principal. Eles dependem de aliases como `@/services`, `@/components/ui` e `@/hooks`, portanto devem viver dentro do projeto React completo quando integrados.

`frontend/services/centralDadosService.ts` e o contrato de comunicacao com Supabase. Ele calcula hash de arquivos, envia XLSX para Storage, chama a Edge Function, acompanha processamento em fatias, promove dados e consulta status da origem real.

`backend/aster_collector` e a camada Python para workers e automacao autorizada. `xlsx_pipeline.py` usa `openpyxl` em modo streaming e entrega blocos pequenos a `pandas`; `browser_capture.py` usa Playwright para abrir o Aster, autenticar e observar respostas de rede.

`supabase/functions/processar-importacao/index.ts` e a funcao server-side de processamento. Ela baixa o XLSX do bucket privado, detecta a aba tabular correta, le linhas em streaming, normaliza valores, grava staging e atualiza checkpoints.

`supabase/migrations` define a base necessaria: catalogo de fontes, mapeamentos, historico, staging, indicadores, bucket `imports`, persistencia de aba XLSX, idempotencia Aster e metadados de captura.

`extension/aster-capture` e uma extensao Chrome Manifest V3. Ela so atua em `https://aster.gruposps.com.br/*`, injeta um hook de pagina, intercepta respostas Fetch/XHR candidatas e envia arrays de objetos para a Edge Function de ingestao configurada pelo operador.

`tools/xlsx` contem utilitarios locais para inspecionar a estrutura de planilhas XLSX sem abrir os arquivos no Excel.

## Decisoes Importantes

- O navegador nao deve parsear planilhas grandes; ele apenas envia o binario ao Storage.
- `pandas` deve ser usado em blocos quando os arquivos forem grandes; `pandas.read_excel()` direto fica reservado para arquivos pequenos.
- Playwright e preferivel para o Aster porque permite navegar no dominio real e capturar Fetch/XHR sem depender de scraping visual fragil.
- A staging preserva `payload_original` para auditoria e `dados_transformados` para promocao.
- Idempotencia e feita por hash de arquivo na tabela `importacoes` e por hash de registro na staging.
- O Aster deve ser tratado como integracao assistida ou backend autorizado ate existir API oficial.
- Secrets ficam em ambiente seguro; nunca em migrations, frontend, extensao ou documentacao.
