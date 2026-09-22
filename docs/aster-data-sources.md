# Fontes de Dados Aster

Catalogo gerado a partir da varredura autenticada dos relatorios visiveis no menu do Aster.

Arquivo tecnico:

```text
docs/evidence/aster_report_contracts.md
```

Matriz de treinamento:

```text
docs/aster-training-matrix.md
```

## Prioridade de Ingestao

| Area | Query ID | Relatorio | Utilidade | Status |
|---|---|---|---|---|
| Pedido / faturamento / vendas | `D0A4D301` | ABR - Analise de Vendas por Item | Vendas/faturamento por item, cliente, filial, nota, vendedor, cidade, margem e impostos | Automatizado, validado e classificado por canal/regiao |
| Comercial executivo | `0F75E84D` | Resumo Comercial | Indicadores consolidados por periodo | Automatizado e validado |
| Comercial / clientes | `027051BD` | Segmentacao de Lead | Base comercial/clientes/leads | Automatizado e validado; 9.568 linhas |
| Preco / cliente | `CAF55C1D` | Ultimo preco de venda | Historico de preco por cliente/item | Automatizado e validado; 50 linhas |
| Estoque | `804C04C1` | Estoque | Posicao de estoque por familia | Probe retornou `PageNotAuthorized` no perfil atual |
| Estoque | `6630A54D` | Estoque Disponivel | Saldo disponivel por familia | Requer familia |
| Estoque | `DBF2AB0E` | Estoque WMS | Estoque WMS por familia | Requer familia |
| Estoque / produto | `6AD70B15` | Estrutura de Produto | Estrutura/BOM por item | Treinado com item real; precisa item com estrutura cadastrada |
| Compras | - | - | Compras/pedidos de compra | Ainda nao apareceu nos 13 relatorios capturados; precisa explorar modulo/permissao |
| Comercial / indicacao | `AB439998` | ABR - Vendas Por Indicacao | Vendas por indicacao no periodo | Executa, mas sem `body.data` em setembro/2026 |
| Transporte | `C1A4D279` | Ocorrencias | Ocorrencias por data/rota/minuta | Requer data de entrega |

## Lacunas

- **Pedidos:** `D0A4D301` traz campos comerciais e fiscais, mas ainda precisamos confirmar se representa pedido, faturamento ou ambos conforme o campo `Tipo`/nota/documento.
- **Estoque:** `804C04C1` bloqueou por permissao; `6630A54D`, `DBF2AB0E` e `A6B5B978` ainda precisam de treino/permite acesso.
- **Compras:** nenhum relatorio claro de compras apareceu nos 13 relatorios capturados. Precisa explorar o modulo `Compras` ou pedir permissao/relatorio.
- **Producao:** nenhum relatorio explicitamente de producao apareceu; `6AD70B15` pode ajudar com estrutura de produto/BOM.

## Estrategia do Robo

1. Priorizar pedido/faturamento/vendas a partir do `D0A4D301`.
2. Classificar vendas por `varejo` e `atacado`, separados por regiao, usando a planilha `Regioes de atendimento`.
3. Usar `027051BD` para base de clientes/leads e apoio a segmentacao comercial.
4. Usar `CAF55C1D` para enriquecer preco por cliente/item.
5. Resolver acesso/alternativa para estoque.
6. Explorar compras somente se nao exigir permissao individual; se exigir, documentar como bloqueio.

## Registro Operacional

As configuracoes de execucao automatica ficam em:

```text
backend/aster_collector/report_registry.py
```

Status atual:

- `D0A4D301`: validado com preenchimento automatico de datas e clique em `Confirmar`.
  - Regra de filtros: `Tipo` vazio significa todos; `Filial` deve ser selecionada como `Todos`.
- `0F75E84D`: validado com preenchimento automatico de datas e clique em `Confirmar`.
- `027051BD`: validado sem filtro; carga real de 9.568 linhas.
- `CAF55C1D`: validado; carga real de 50 linhas.
- `37D9E431`: fora da prioridade atual.
- `804C04C1`: bloqueado por permissao (`PageNotAuthorized`) no perfil atual.
- `AB439998`, `6AD70B15`, `A6B5B978`, `6630A54D`, `DBF2AB0E`: seguem em treinamento/descoberta.

## Classificacao Varejo / Atacado

A referencia de regioes veio da planilha Google `Regioes de atendimento`, com abas `Varejo` e `Atacado`.

O conhecimento esta codificado em:

```text
backend/aster_collector/commercial_regions.py
```

Resumo gerado dos dados Aster atuais:

```text
docs/evidence/aster_sales_regions_summary.md
```

## Scripts Relacionados

```powershell
.\.venv\Scripts\python.exe tools\aster_probe_all_reports.py
.\.venv\Scripts\python.exe tools\aster_live_execute_ingest.py
.\.venv\Scripts\python.exe tools\check_aster_ingestion.py
.\.venv\Scripts\python.exe tools\aster_training_samples.py
.\.venv\Scripts\python.exe tools\build_aster_training_matrix.py
.\.venv\Scripts\python.exe tools\summarize_aster_sales_regions.py
```
