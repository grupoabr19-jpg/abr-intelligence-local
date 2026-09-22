# Matriz de Treinamento Aster

Esta matriz e gerada a partir dos contratos capturados, do registro operacional do robo e das evidencias de execucao/probe.

| Area | Query ID | Relatorio | Status | Ultima leitura | Observacao |
|---|---|---|---|---|---|
| comercial_clientes | `027051BD` | Segmentacao de Lead | validated | 9568 linhas; ASTER-027051BD-1790101643 | Parametro CardCode opcional; validado sem filtro com base comercial/clientes. |
| comercial_executivo | `0F75E84D` | Resumo Comercial | validated | 16 linhas; ASTER-0F75E84D-1790087326 | Fonte validada para indicadores comerciais consolidados. |
| financeiro | `37D9E431` | ABR - Contas a Receber - PN | deprioritized | - | Fora da prioridade atual; manter apenas como referencia financeira eventual. |
| estoque | `6630A54D` | Estoque Disponivel | training | - | Requer FAMILIA; usa opcao agregada TODAS AS FAMILIAS. |
| estoque_produto | `6AD70B15` | Estrutura de Produto | training | - | Usa item real aprendido do relatorio de vendas para treino inicial. |
| estoque | `804C04C1` | Estoque | training | - | Requer FAMILIA; usa opcao agregada TODAS AS FAMILIAS. |
| outros | `897A37D9` | Mapa de relacao | candidate | - | Precisa avaliar utilidade analitica. |
| estoque | `A6B5B978` | Estoque URIFER | needs_ui_discovery | - | Contrato capturado sem parametros obrigatorios, mas a UI ainda nao disparou execute automatico. |
| comercial_vendas | `AB439998` | ABR - Vendas Por Indicacao | candidate | - | Executou em janela curta sem body.data; precisa testar periodo maior. |
| transporte | `C1A4D279` | Ocorrencias | candidate | - | Requer data de entrega; rota/minuta sao opcionais. |
| preco_cliente | `CAF55C1D` | Ultimo preco de venda | validated | 50 linhas; ASTER-CAF55C1D-1790101717 | Validado com retorno de dados; filtros queryField podem retornar nulos quando o relatorio autoexecuta. |
| comercial_vendas | `D0A4D301` | ABR - Analise de Vendas por Item | validated | 154 linhas; ASTER-D0A4D301-1790100438 | Tipo vazio representa todos; filial deve ser selecionada como Todos pelo dropdown. |
| estoque | `DBF2AB0E` | Estoque WMS | training | - | Requer FAMILIA; usa opcao agregada TODAS AS FAMILIAS. |

## Regras Aprendidas

- `D0A4D301`: `Tipo` vazio representa todos; `Filial` deve ser selecionada como `Todos` pelo dropdown.
- `0F75E84D`: datas simples nas posicoes 0 e 1.
- `37D9E431`: fora da prioridade atual; contas a receber nao deve guiar o treino principal.
- Vendas do `D0A4D301` sao classificadas por varejo/atacado e regiao com `backend/aster_collector/commercial_regions.py`.
- Relatorios de estoque com `FAMILIA` exigem permissao e/ou queryField; `804C04C1` retornou `PageNotAuthorized` no probe atual.