# Stack Python Recomendada

## Bibliotecas

- `pandas`: transformacoes tabulares, validacoes e agregacoes.
- `openpyxl`: leitura XLSX em modo streaming, evitando carregar tudo em memoria.
- `pyarrow`: formato colunar eficiente para cache ou troca intermediaria.
- `playwright`: automacao autorizada do portal Aster e observacao de rede.
- `httpx`: envio assíncrono de lotes para Edge Functions/APIs.
- `pydantic-settings`: configuracao via `.env`.
- `tenacity`: retentativas com backoff para chamadas de rede.

## Regra Para XLSX Grande

Evite:

```python
pandas.read_excel("arquivo_grande.xlsx")
```

Prefira:

```python
from backend.aster_collector.xlsx_pipeline import iter_xlsx_frames

for frame in iter_xlsx_frames("arquivo_grande.xlsx", chunk_size=5000):
    # limpar, validar, transformar e enviar o bloco
    ...
```

## Regra Para Aster

O coletor deve tentar capturar dados nesta ordem:

1. API oficial fornecida pela SPS Group.
2. Chamadas Fetch/XHR observadas pelo Playwright apos login autorizado.
3. Exportacao de relatorio gerada pelo proprio Aster.
4. Scraping visual da tela apenas como ultimo recurso.

Essa ordem reduz fragilidade e facilita auditoria.

## Exploração do Aster

Antes de automatizar downloads, rode o explorador:

```powershell
.\.venv\Scripts\python.exe -m backend.aster_collector.cli explore-aster --max-clicks 30
```

Ele gera:

- `docs/evidence/aster_exploration.json`
- `docs/evidence/aster_exploration.md`

Esses arquivos devem ser usados como mapa para decidir quais relatórios e endpoints o robô deve baixar.
