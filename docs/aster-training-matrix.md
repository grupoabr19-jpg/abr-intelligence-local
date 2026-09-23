# Matriz de Treinamento Aster

Esta matriz e gerada a partir dos contratos capturados, do registro operacional do robo e das evidencias de execucao/probe.

| Area | Query ID | Relatorio | Status | Entregaveis | Ultima leitura | Observacao |
|---|---|---|---|---|---|---|
| comercial_clientes | `027051BD` | Segmentacao de Lead | validated | `cadastro_clientes` | 9575 linhas; ASTER-027051BD-1790171538 | Parametro CardCode opcional; validado sem filtro com base comercial/clientes. A tela pode autoexecutar sem botao visivel. |
| comercial_executivo | `0F75E84D` | Resumo Comercial | validated | `vendas_faturamento` | 16 linhas; ASTER-0F75E84D-1790170415 | Fonte validada para indicadores comerciais consolidados. |
| financeiro | `37D9E431` | ABR - Contas a Receber - PN | deprioritized | `financeiro_recebiveis` | - | Fora da prioridade atual; manter apenas como referencia financeira eventual. |
| estoque | `6630A54D` | Estoque Disponivel | validated | `estoque` | 3610 linhas; ASTER-6630A54D-1790172377 | Validado com FAMILIA agregada TODAS AS FAMILIAS; retorno de 3.610 linhas e 14 colunas. |
| estoque_produto | `6AD70B15` | Estrutura de Produto | validated_empty | `cadastro_produtos` | - | Pagina abre sem registros uteis para coletar no escopo atual. |
| estoque | `804C04C1` | Estoque | validated | `estoque` | 3280 linhas; ASTER-804C04C1-1790176945 | Validado com execute direto; FAMILIA TODAS AS FAMILIAS retornou 3.280 linhas e 13 colunas. |
| outros | `897A37D9` | Mapa de relacao | validated_empty | - | - | Pagina/execucao validada sem registros uteis no cenario atual. |
| estoque | `A6B5B978` | Estoque URIFER | validated_empty | `estoque` | - | Execute validado sem parametros; retorno atual veio sem colunas e sem dados. |
| comercial_vendas | `AB439998` | ABR - Vendas Por Indicacao | validated_empty | - | 0 linhas; ASTER-AB439998-1790181337 | Executa com datas e Confirmar, mas o periodo validado retornou Nenhum registro encontrado. |
| transporte | `C1A4D279` | Ocorrencias | validated | `logistica_frete` | 93 linhas; ASTER-C1A4D279-1790177327 | Validado com Data de Entrega; rota/minuta opcionais retornaram 93 linhas e 16 colunas. |
| preco_cliente | `CAF55C1D` | Ultimo preco de venda | validated | `vendas_faturamento` | 50 linhas; ASTER-CAF55C1D-1790171088 | Validado com retorno de dados; apos preencher filtros pode autoexecutar sem botao visivel e retornar filtros nulos. |
| comercial_vendas | `D0A4D301` | ABR - Analise de Vendas por Item | validated | `vendas_faturamento`, `pedidos_carteira`, `cadastro_clientes`, `devolucoes_cancelamentos`, `logistica_frete` | 154 linhas; ASTER-D0A4D301-1790169979 | Tipo vazio representa todos; filial deve ser selecionada como Todos pelo dropdown. |
| estoque | `DBF2AB0E` | Estoque WMS | validated | `estoque` | 3389 linhas; ASTER-DBF2AB0E-1790174271 | Validado com execute direto; FAMILIA TODAS AS FAMILIAS retornou 3.389 linhas e 12 colunas sem intervencao. |

## Escopo Solicitado

O robo deve entregar as bases abaixo em formato granular, preservando codigos, datas, quantidades e valores em colunas separadas.

| Base | Prioridade | Atualizacao | Grao | Fontes conhecidas | Lacunas |
|---|---|---|---|---|---|
| Vendas e faturamento por item | prioridade_1 | diaria | uma linha por item de nota fiscal ou item vendido | `D0A4D301`, `0F75E84D`, `CAF55C1D`, `drive:margem_resumo_latest` | - |
| Cotacoes e orcamentos | prioridade_1 | diaria | uma linha por item cotado | - | Ainda nao ha relatorio de cotacoes/orcamentos identificado no menu capturado. |
| Pedidos e carteira | prioridade_1 | diaria | uma linha por item de pedido | `D0A4D301`, `drive:gestao_producao_latest` | Confirmar se D0A4D301 cobre pedidos abertos/parcialmente faturados ou apenas faturamento.<br>A planilha Gestão da Produção deve ser inspecionada como fonte complementar de carteira/pedido/item. |
| Estoque por produto e unidade | prioridade_1 | diaria | fotografia periodica por produto, unidade, deposito e lote quando existir | `804C04C1`, `6630A54D`, `DBF2AB0E`, `A6B5B978` | Base operacional coberta por 804C04C1, 6630A54D e DBF2AB0E; A6B5B978 foi validado sem registros/colunas no cenario atual.<br>Confirmar se todos os campos financeiros de estoque, lote e datas de ultima movimentacao existem nas colunas retornadas. |
| Compras por fornecedor e produto | prioridade_2 | diaria ou semanal | uma linha por item de pedido de compra ou nota de entrada | - | Nenhum relatorio claro de compras apareceu nos 13 relatorios capturados. |
| Cadastro completo de produtos | prioridade_1 | semanal/mensal | uma linha por SKU/produto | `6AD70B15`, `drive:gestao_producao_latest`, `drive:margem_resumo_latest` | Ainda falta relatorio cadastral completo de produtos; 6AD70B15 cobre estrutura/BOM, nao cadastro completo.<br>A planilha Gestão da Produção traz item do PA/MP por pedido; a planilha de margem traz Apoio, BD_Meta e Tabela de Preço para atributos operacionais de produto/SKU. |
| Cadastro completo de clientes | prioridade_1 | semanal/mensal | uma linha por cliente | `027051BD`, `D0A4D301` | - |
| Devolucoes e cancelamentos | prioridade_2 | diaria | uma linha por item devolvido ou cancelado | `D0A4D301` | Confirmar se os motivos existem em modulo/tabela propria ou em relatorio separado. |
| Financeiro e recebiveis | prioridade_2 | diaria | uma linha por titulo/parcela ou documento financeiro | `37D9E431` | 37D9E431 esta depriorizado, mas deve voltar quando a base comercial estiver coberta. |
| Logistica e frete | prioridade_2 | diaria | uma linha por pedido/entrega/ocorrencia logistica | `C1A4D279`, `D0A4D301`, `drive:gestao_producao_latest` | C1A4D279 cobre ocorrencias.<br>A planilha Gestão da Produção traz Transportadora, Valor Frete, romaneio e datas logisticas; ainda falta confirmar rota/distancia. |

## Fontes Externas Complementares

| Fonte | Regra | Arquivo local | Cobertura provavel | Observacao |
|---|---|---|---|---|
| `drive:margem_resumo_latest` | Sempre usar o arquivo mais recente da pasta por modified_time. | `Planilhas/Margem_GABR_20260916.xlsx` | `vendas_faturamento`, `cadastro_produtos` | Fonte complementar local para margem, custo, preco medio, tabela de preco e resumo comercial quando o Aster nao trouxer todos os campos. |
| `drive:gestao_producao_latest` | Sempre usar o arquivo mais recente da pasta por modified_time. | `Planilhas/Gestão da Produção.xlsx` | `pedidos_carteira`, `cadastro_produtos`, `logistica_frete` | Fonte complementar local para pedido, item, carteira, producao/PCP, picking, NF, frete e dados de produto usados na operacao. |

## Regras de Extracao

- Preferir CSV ou Excel quando nao houver API/banco disponivel.
- Manter uma linha por transacao/item; evitar consolidacoes, totais e subtotais misturados.
- Preservar codigos unicos de cliente, produto, pedido e fornecedor.
- Manter datas em campos proprios e valores/quantidades em colunas separadas.
- Quando um campo nao existir, registrar informacao equivalente, modulo/tabela, relatorio disponivel ou necessidade de consulta especifica.
- Nesta etapa, priorizar identificar quais dados ja existem no ERP e como podem ser extraidos.

## Regras Aprendidas

- `D0A4D301`: `Tipo` vazio representa todos; `Filial` deve ser selecionada como `Todos` pelo dropdown.
- `0F75E84D`: datas simples nas posicoes 0 e 1.
- `37D9E431`: financeiro e recebiveis sao prioridade secundaria; nao devem bloquear o treino comercial principal.
- Vendas do `D0A4D301` sao classificadas por varejo/atacado e regiao com `backend/aster_collector/commercial_regions.py`.
- Relatorios de estoque com `FAMILIA` exigem permissao e/ou queryField; `804C04C1` retornou `PageNotAuthorized` no probe atual.