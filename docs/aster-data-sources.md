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
| Estoque | `804C04C1` | Estoque | Posicao de estoque por familia | Automatizado e validado por execute direto |
| Estoque | `6630A54D` | Estoque Disponivel | Saldo disponivel por familia | Automatizado e validado com familia agregada |
| Estoque | `DBF2AB0E` | Estoque WMS | Estoque WMS por familia | Automatizado e validado por execute direto |
| Estoque / produto | `6AD70B15` | Estrutura de Produto | Estrutura/BOM por item | Executa, mas sem registros uteis no cenario atual |
| Compras | - | - | Compras/pedidos de compra | Ainda nao apareceu nos 13 relatorios capturados; precisa explorar modulo/permissao |
| Comercial / indicacao | `AB439998` | ABR - Vendas Por Indicacao | Vendas por indicacao no periodo | Executa, mas sem `body.data` em setembro/2026 |
| Transporte | `C1A4D279` | Ocorrencias | Ocorrencias por data/rota/minuta | Requer data de entrega |
| Planilha local | `drive:gestao_producao_latest` | Gestao da Producao | Pedido, item, carteira, producao/PCP, NF, picking, frete e transportadora | Arquivo local em `Planilhas/Gestão da Produção.xlsx` |
| Planilha local | `drive:margem_resumo_latest` | Margem GABR | Margem, custo, preco medio, tabela de preco e atributos operacionais de produto | Arquivo local em `Planilhas/Margem_GABR_20260916.xlsx` |

## Escopo Completo Solicitado

O treinamento do robo deve cobrir estas bases em formato granular, sem totais ou subtotais misturados:

| Base | Frequencia desejada | Fontes Aster conhecidas | Situacao |
|---|---|---|---|
| Vendas e faturamento por item | diaria | `D0A4D301`, `0F75E84D`, `CAF55C1D`, `drive:margem_resumo_latest` | Base principal validada; planilha de margem complementa custo, margem, preco e metas. |
| Cotacoes e orcamentos | diaria | - | Pendente descobrir relatorio, modulo, tabela ou exportacao equivalente. |
| Pedidos e carteira | diaria | `D0A4D301`, `drive:gestao_producao_latest` | Planilha local cobre pedido/item/status/carteira/producao; usar para separar pedido vs faturamento. |
| Estoque por produto/unidade | diaria | `804C04C1`, `6630A54D`, `DBF2AB0E`, `A6B5B978` | Estoque principal validado em tres relatorios; `A6B5B978` validado vazio. |
| Compras por fornecedor/produto | diaria ou semanal | - | Pendente explorar modulo de compras ou solicitar permissao/relatorio. |
| Cadastro de produtos | semanal/mensal | `6AD70B15`, `drive:gestao_producao_latest`, `drive:margem_resumo_latest` | Planilhas locais trazem item, familia, grupo, qualidade, tabela de preco e atributos operacionais; NCM completo ainda depende do Aster/vendas. |
| Cadastro de clientes | semanal/mensal | `027051BD`, `D0A4D301` | Base de segmentacao validada; validar campos cadastrais completos. |
| Devolucoes e cancelamentos | diaria | `D0A4D301` | Confirmar status/motivos ou relatorio proprio. |
| Financeiro e recebiveis | diaria | `37D9E431` | Prioridade secundaria; manter para cruzar venda, prazo e qualidade financeira. |
| Logistica e frete | diaria | `C1A4D279`, `D0A4D301`, `drive:gestao_producao_latest` | Planilha local traz transportadora, valor frete, romaneio e datas logisticas; rota/distancia ainda pendente. |

As regras e campos completos ficam codificados em `backend/aster_collector/data_requirements.py` e sao publicados em `docs/aster-training-matrix.md` e no endpoint `/v1/aster/requirements`.

## Lacunas

- **Cotacoes/orcamentos:** ainda nao apareceu fonte explicita para demanda antes do pedido/faturamento; as planilhas locais nao trouxeram coluna clara de orcamento/cotacao.
- **Pedidos:** `Gestão da Produção.xlsx` cobre pedido, item, status, data de entrega, draft, NF, picking e producao; usar como fonte principal de carteira.
- **Estoque:** `804C04C1`, `6630A54D` e `DBF2AB0E` estao validados; `A6B5B978` executa vazio.
- **Compras:** nenhum relatorio claro de compras apareceu nos 13 relatorios capturados. Precisa explorar o modulo `Compras` ou pedir permissao/relatorio.
- **Produtos:** planilhas locais cobrem cadastro operacional/preco; NCM aparece em `D0A4D301`, mas ainda falta cadastro mestre completo.
- **Devolucoes/cancelamentos:** confirmar motivo e status em relatorio proprio ou campo equivalente.
- **Financeiro/logistica:** manter como prioridade secundaria, mas dentro do escopo solicitado.

## Estrategia do Robo

1. Priorizar pedido/faturamento/vendas a partir do `D0A4D301`.
2. Classificar vendas por `varejo` e `atacado`, separados por regiao, usando a planilha `Regioes de atendimento`.
3. Usar `027051BD` para base de clientes/leads e apoio a segmentacao comercial.
4. Usar `CAF55C1D` para enriquecer preco por cliente/item.
5. Usar as planilhas locais como camada complementar para carteira, frete, producao, preco e margem.
6. Procurar fontes de cotacao/orcamento e compras apenas se forem exigidas fora do escopo atual disponivel.
7. Se um campo solicitado nao existir, registrar equivalente, modulo/tabela, relatorio disponivel ou necessidade de consulta especifica.

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
- `804C04C1`, `6630A54D`, `DBF2AB0E`: validados para estoque.
- `AB439998`, `6AD70B15`, `A6B5B978`, `897A37D9`: validados como vazios/sem registros uteis no cenario atual.
- `Planilhas/Gestão da Produção.xlsx`: fonte local validada por estrutura, com 45.390 linhas e 59 colunas.
- `Planilhas/Margem_GABR_20260916.xlsx`: fonte local validada por estrutura, com abas de margem, apoio, metas e tabela de preco.

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
