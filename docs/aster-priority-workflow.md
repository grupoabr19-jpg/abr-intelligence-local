# Workflow Prioritario Aster

Este workflow substitui a prioridade anterior de financeiro/contas a receber.

## Prioridades

1. **Pedido**
   - Objetivo: identificar pedidos, itens, cliente, vendedor, cidade, filial, status e valores.
   - Fonte atual: `D0A4D301`, enquanto nao houver relatorio especifico de pedido.
   - Ponto a confirmar: diferenciar pedido aberto, faturado, devolucao e venda perdida pelo campo `Tipo`/documento.

2. **Faturamento**
   - Objetivo: notas, valor faturado, impostos, receita liquida, margem e periodo.
   - Fonte atual: `D0A4D301`.
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
   - Bloqueio atual: `804C04C1` retornou `PageNotAuthorized`.

5. **Compras**
   - Objetivo: pedidos de compra, fornecedores, entrada, compras em aberto.
   - Status: ainda nao apareceu nos 13 relatorios capturados.
   - Proximo passo: explorar modulo `Compras` no Aster. Se pedir permissao individual, documentar bloqueio.

## Fora de Prioridade

- `37D9E431` / Contas a Receber - PN.
- Financeiro so deve voltar se ajudar diretamente a reconciliar faturamento/pedido.

## Treino Atual Validado

| Query ID | Relatorio | Uso |
|---|---|---|
| `D0A4D301` | ABR - Analise de Vendas por Item | Pedido/faturamento/vendas/margem/canal/regiao |
| `0F75E84D` | Resumo Comercial | Indicadores consolidados |
| `027051BD` | Segmentacao de Lead | Base comercial/clientes |
| `CAF55C1D` | Ultimo preco de venda | Preco cliente/item |

## Proximas Acoes do Robo

1. Melhorar a classificacao das linhas indefinidas no resumo de canal/regiao.
2. Explorar relatorios de estoque com outros IDs e registrar se o bloqueio e permissao ou parametro.
3. Procurar relatorios de compras no menu/modulo de compras.
4. Separar claramente pedido vs faturamento dentro do `D0A4D301`.

## API / Deploy

O backend de extracao roda como API FastAPI em container Docker no Render.

Arquivos:

```text
Dockerfile
render.yaml
docs/api.md
```
