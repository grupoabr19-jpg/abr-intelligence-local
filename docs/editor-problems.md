# Problemas do VS Code

Este workspace e um recorte organizado do ABR Intelligence, nao o app completo. Por isso, o painel **Problems** do VS Code pode mostrar centenas de erros que sao falsos positivos de contexto.

## Causas Mais Provaveis

- Arquivos TS/TSX em `frontend/` dependem do projeto React completo, incluindo aliases `@/`, componentes UI, hooks, `react-router-dom`, `lucide-react` e cliente Supabase.
- A Edge Function em `supabase/functions/processar-importacao/index.ts` depende do runtime Deno/Supabase.
- O backend Python depende das bibliotecas listadas em `requirements.txt`.
- `docs/reference/`, `data/input/` e `archive/` sao referencia/artefatos, nao codigo que deve ser analisado pelo editor.

## Configuracao Aplicada

`.vscode/settings.json` reduz o ruido do editor:

- esconde `archive`, `data/input` e caches Python;
- exclui referencias antigas da busca;
- desativa validacao TypeScript/JavaScript neste recorte;
- limita a analise Python aos arquivos relevantes.

## Como Validar o Que Importa Agora

Python:

```powershell
py -3 -m py_compile backend\aster_collector\__init__.py backend\aster_collector\settings.py backend\aster_collector\xlsx_pipeline.py backend\aster_collector\browser_capture.py backend\aster_collector\cli.py tools\xlsx\inspect_xlsx_headers.py tools\xlsx\inspect_xlsx_structure.py tools\xlsx\patch_xlsx_sheet_selection.py
```

Extensao Chrome:

```powershell
Get-Content -Raw extension\aster-capture\manifest.json | ConvertFrom-Json | Out-Null
```

## Quando Reativar TypeScript

Reative `typescript.validate.enable` quando o app React completo estiver presente com:

- `package.json`;
- `tsconfig.json`;
- `node_modules`;
- `src/` completo;
- alias `@/` configurado;
- componentes UI e hooks reais.
