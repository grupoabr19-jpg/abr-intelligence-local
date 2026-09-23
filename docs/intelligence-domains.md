# Dominios de Inteligencia

O ABR Intelligence passa a separar as fontes em dois dominios principais para evitar mistura entre operacao interna e sinais de mercado.

## Inteligencia Interna

Escopo atual:

- Relatorios Aster treinados e validados.
- Planilhas locais em `Planilhas/`.
- Regras de regiao e canal comercial.
- Staging, historico de cargas e evidencias operacionais.

Exemplos de bases internas:

- Vendas, faturamento e ultimo preco de venda.
- Pedidos, carteira e producao.
- Estoque Aster, WMS e URIFER.
- Clientes, produtos, margem, frete e ocorrencias.

Regra: toda fonte deste dominio precisa representar operacao interna da ABR ou arquivo operacional mantido pela equipe.

## Inteligencia Externa

Escopo reservado para a proxima fase:

- Mercado nacional do aco.
- Mercado internacional do aco.
- Cotacoes e referencias de preco de aco.
- Cambio, commodities, sucata, frete e outros indicadores.

Regra: coletores externos devem ficar separados da automacao Aster e das planilhas internas. Depois os dados podem ser cruzados na camada analitica, mas a origem deve continuar identificavel.

## API

O endpoint protegido abaixo publica essa divisao:

```http
GET /v1/intelligence/domains
```

Use esse contrato como referencia para novas rotas. Coletas internas devem continuar em namespaces como `/v1/aster/*` e `/v1/spreadsheets/*`; coletas futuras de mercado devem usar um namespace separado, por exemplo `/v1/external/*`.
