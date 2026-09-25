# Status do Contrato Oficial - Modulo Atendimento

Data: 2026-09-25

Este documento corrige a leitura anterior: os batches oficiais sao 00 a 17.

## Status por batch

| Batch | Status | Observacao |
|---|---|---|
| 00 - Auditoria | Concluido | `docs/atendimento/00_arquitetura_atual.md` criado. |
| 01 - Ingestao e RAW | Parcial | RAW Kommo principal existe. Foram criadas tabelas RAW oficiais faltantes, mas Aster/Producao/Ranking/Metas ainda precisam de carga real. |
| 02 - Dimensoes mestres | Parcial | Criadas `dim_colaborador`, `dim_cliente`, `dim_polo`, `dim_funil`, `dim_etapa`, `dim_data`. Falta validar cliente canonico e representantes. |
| 03 - Kommo tratado | Parcial | Criadas/populadas `fact_kommo_leads`, `fact_kommo_tasks`, `fact_kommo_interacoes`. Interacoes dependem de eventos que casem com leads ativos. |
| 04 - Aster + Producao tratados | Estrutura criada | `fact_sales`, `fact_orders`, `fact_order_items`, `fact_production` criadas. Falta promocao dos dados reais. |
| 05 - Bridge Kommo x ERP | Estrutura criada | `bridge_lead_order` criada. Falta regra de match A/B/C/D. |
| 06 - Ranking | Parcial | Ranking atual existe por fatos Kommo, mas ainda nao cruza ERP/metas do contrato. |
| 07 - Visao Geral | Parcial | KPIs Kommo e agregados existem. Pedidos/toneladas/receita dependem de Batch 04/05 completos. |
| 08 - SLA | Parcial | SLA preparado, mas a fonte ainda nao possui campos suficientes: 1000 leads sem SLA calculavel. |
| 09 - Clientes | Pendente | Requer chave canonica de cliente e cruzamento Aster + Kommo + Producao. |
| 10 - Pedidos | Estrutura criada | Facts criadas, faltam metricas oficiais por pedido distinto. |
| 11 - Entregas | Pendente | Depende de validar data real de entrega. |
| 12 - Ocorrencias | Parcial | `fact_occurrences` criada/populada para sem resposta/follow-up. Faltam ocorrencias de pedido/producao/entrega. |
| 13 - Origens & Canais | Parcial | Origem Kommo existe. Canal real ainda nao deve ser inferido. |
| 14 - Equipe | Parcial | Blocos Varejo/Atacado/Representantes no frontend. Atividade por mensagens depende de eventos validos. |
| 15 - Reclamacoes | Nao implementar | Documento oficial manda aguardar campo estruturado. |
| 16 - Satisfacao | Nao implementar | Documento oficial manda aguardar pesquisa real. |
| 17 - Qualidade/Auditoria/Performance | Parcial | `data_quality_alerts`, agregados e docs existem. Falta cobertura completa de testes e tooltips de todos KPIs. |

## Objetos criados para alinhar ao protocolo

- `raw_kommo_contacts`
- `raw_kommo_companies`
- `raw_aster_sales`
- `raw_aster_orders`
- `raw_production`
- `raw_ranking`
- `raw_targets`
- `dim_colaborador`
- `dim_cliente`
- `dim_polo`
- `dim_funil`
- `dim_etapa`
- `dim_data`
- `fact_kommo_leads`
- `fact_kommo_interacoes`
- `fact_kommo_tasks`
- `fact_sales`
- `fact_orders`
- `fact_order_items`
- `fact_production`
- `bridge_lead_order`
- `fact_occurrences`
- `data_quality_alerts`
- `colaboradores_nao_mapeados`

## Ultima validacao executada

`tools/refresh_atendimento_official_contract.py` retornou:

```json
{
  "fact_kommo_leads": 894,
  "fact_kommo_tasks": 5,
  "fact_kommo_interacoes": 0,
  "fact_occurrences": 270,
  "colaboradores_nao_mapeados": 3
}
```

## Pendencias criticas

1. Carregar RAW oficial de Aster, Producao, Ranking e Metas.
2. Promover Aster para `fact_sales`, `fact_orders`, `fact_order_items`.
3. Promover Gestao da Producao para `fact_production`.
4. Implementar `bridge_lead_order` com niveis A/B/C/D.
5. Validar campo real de entrega antes de Batch 11.
6. Validar fonte estruturada para reclamacoes e satisfacao antes de Batches 15 e 16.
7. Resolver 3 colaboradores nao mapeados.
8. Obter eventos/mensagens que casem com leads ativos para preencher `fact_kommo_interacoes`.
