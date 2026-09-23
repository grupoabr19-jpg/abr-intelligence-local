# Workflow Prioritario Aster

Este workflow substitui a prioridade anterior de financeiro/contas a receber.

## Prioridades

1. **Pedido**
   - Objetivo: identificar pedidos, itens, cliente, vendedor, cidade, filial, status e valores.
   - Fonte atual: `Planilhas/Gestão da Produção.xlsx`, com apoio do `D0A4D301`.
   - Campos uteis ja vistos: `Pedido`, `Item do PA`, `Status da Linha`, `Qtd Pedido`, `Peso`, `Total`, `Data Entrega PV`, `Num. Draft`, `NF`, `Fat R$`.

2. **Faturamento**
   - Objetivo: notas, valor faturado, impostos, receita liquida, margem e periodo.
   - Fonte atual: `D0A4D301`, com apoio de `Planilhas/Margem_GABR_20260916.xlsx`.
   - Campos uteis ja vistos: `N° NF`, `Valor Total`, `Data Venda`, `TotalImpostos`, `RecLiquida`, `EBITDA`, `Filial`, `Vendedor`.

3. **Vendas por canal e regiao**
   - Objetivo: separar `varejo` e `atacado`, ambos por regiao.
   - Fonte de vendas: `D0A4D301`.
   - Fonte de regras: planilha `Regioes de atendimento`.
   - Codigo: `backend/aster_collector/commercial_regions.py`.
   - Saida atual: `docs/evidence/aster_sales_regions_summary.md`.

4. **Estoque**
   - Objetivo: saldo, disponibilidade e familia.
   - Candidatos: `6630A54D`, `804C04C1`, `DBF2AB0E`, `A6B5B978`.
   - Status atual: `6630A54D`, `804C04C1` e `DBF2AB0E` validados; `A6B5B978` validado vazio.

5. **Compras**
   - Objetivo: pedidos de compra, fornecedores, entrada, compras em aberto.
   - Status: ainda nao apareceu nos 13 relatorios capturados.
   - Proximo passo: explorar modulo `Compras` no Aster. Se pedir permissao individual, documentar bloqueio.

6. **Cotacoes / orcamentos**
   - Objetivo: medir demanda antes do faturamento, kg cotados, taxa de conversao e perdas por motivo/concorrente.
   - Status: ainda nao apareceu relatorio correspondente no menu capturado nem nas duas planilhas locais inspecionadas.
   - Proximo passo: tratar como lacuna por permissao/alimentacao ate existir exportacao especifica.

7. **Cadastros**
   - Objetivo: clientes e produtos completos para enriquecer vendas, estoque, margem e mercado externo por NCM.
   - Fonte atual clientes: `027051BD` e enriquecimento em `D0A4D301`.
   - Fonte atual produtos: `Planilhas/Margem_GABR_20260916.xlsx` (`Apoio`, `BD_Meta`, `Tabela de Preço`) e `Gestão da Produção.xlsx`; `6AD70B15` executa vazio.

8. **Devolucoes, financeiro e logistica**
   - Objetivo: medir perdas comerciais/operacionais, prazo real, inadimplencia e custo logistico.
   - Fontes atuais: `D0A4D301`, `37D9E431` e `C1A4D279`.
   - Regra: sao prioridade secundaria, mas fazem parte do escopo solicitado e devem ser documentadas como cobertas ou pendentes.

## Treino Atual Validado

| Query ID | Relatorio | Uso |
|---|---|---|
| `D0A4D301` | ABR - Analise de Vendas por Item | Pedido/faturamento/vendas/margem/canal/regiao |
| `0F75E84D` | Resumo Comercial | Indicadores consolidados |
| `027051BD` | Segmentacao de Lead | Base comercial/clientes |
| `CAF55C1D` | Ultimo preco de venda | Preco cliente/item |
| `Planilhas/Gestão da Produção.xlsx` | Gestao da Producao | Pedido/item/carteira/producao/picking/NF/frete |
| `Planilhas/Margem_GABR_20260916.xlsx` | Margem GABR | Margem/custo/preco/tabela de preco/produto |

## Proximas Acoes do Robo

1. Melhorar a classificacao das linhas indefinidas no resumo de canal/regiao.
2. Criar ingestao local recorrente para `Gestão da Produção.xlsx`.
3. Criar ingestao local recorrente para `Margem_GABR_20260916.xlsx`.
4. Separar claramente pedido/carteira vs faturamento usando `Gestão da Produção.xlsx` + `D0A4D301`.
5. Confirmar cadastro completo de produtos, principalmente NCM, atributos tecnicos e status ativo/inativo.
6. Para qualquer campo inexistente, registrar equivalente, modulo/tabela, relatorio disponivel ou necessidade de consulta especifica.

## API / Deploy

O backend de extracao roda como API FastAPI em container Docker no Render.

Arquivos:

```text
Dockerfile
render.yaml
docs/api.md
```
