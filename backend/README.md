# Backend Python

Esta pasta concentra a camada Python proposta para duas responsabilidades:

1. processar, validar e transformar arquivos operacionais com bibliotecas de dados;
2. navegar no Aster de forma autorizada usando Playwright quando nao houver API oficial.

## Dependencias

Instale em um ambiente virtual:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Modulos

- `aster_collector/settings.py`: configuracao por variaveis de ambiente.
- `aster_collector/browser_capture.py`: abre o Aster, autentica e observa respostas de rede.
- `aster_collector/xlsx_pipeline.py`: le XLSX em modo streaming e entrega blocos pequenos para pandas.
- `aster_collector/cli.py`: comandos de linha para inspecao inicial.

## Cuidados

- Playwright deve rodar com credenciais em ambiente seguro, nunca no frontend.
- `pandas.read_excel()` carrega a planilha inteira; para arquivos grandes, prefira `openpyxl` em modo `read_only` e converta blocos pequenos em `DataFrame`.
- A captura do Aster deve priorizar observar chamadas Fetch/XHR e contratos reais da aplicacao, nao fazer scraping visual de tabela sempre que houver JSON disponivel.

## Login Assistido no Aster

Para evitar falhas por seletores ou comportamento anti-automacao, use login humano assistido:

```powershell
.\.venv\Scripts\python.exe -m backend.aster_collector.cli manual-login-aster --timeout-seconds 600
```

O Chromium abre visivel. Faca login manualmente e selecione a empresa quando o Aster pedir. O estado de sessao sera salvo em `.auth/aster_session.json`, que nao deve ser versionado.
