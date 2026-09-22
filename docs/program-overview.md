# Visao Funcional do Programa

## Proposito

ABR Intelligence existe para responder, diariamente, perguntas de decisao sobre venda, margem, estoque, producao, compras e mercado. A ideia central e:

```text
dados internos + mercado + inteligencia analitica -> diagnostico -> previsao -> acao
```

## Perguntas Que o Sistema Deve Responder

- Quanto vendemos e faturamos?
- Qual margem estamos conseguindo?
- Qual preco medio estamos praticando?
- Quais produtos ganham ou perdem margem?
- Onde estamos perdendo vendas?
- Quanto temos em estoque e ha quanto tempo esta parado?
- O que esta vendido e ainda nao foi expedido?
- Onde existem atrasos ou gargalos de producao?
- O que estamos comprando, de quem e a qual preco?
- O preco do aco, dolar, frete ou sucata aumenta risco de compra?
- Precisamos comprar agora, esperar, aumentar preco ou reduzir estoque?

## Modulos Esperados

1. **Cockpit Executivo**: visao curta de faturamento, toneladas, margem, estoque, pedidos, producao, expedicao, meta e previsao de fechamento.
2. **Comercial**: analise por empresa, mercado, regiao, vendedor, cliente e produto.
3. **Estoque**: cobertura, giro, idade media, risco de ruptura, excesso e estoque morto.
4. **Compras**: radar de oportunidade com estoque, demanda, preco fornecedor, mercado, dolar, frete e lead time.
5. **Inteligencia Externa do Aco**: series de mercado nacional e internacional para contextualizar decisoes.
6. **Central de Dados**: entrada, auditoria, processamento e promocao de dados.
7. **Integracao Aster**: preferencialmente por API oficial; se indisponivel, por captura assistida autorizada.
8. **Camada Analitica/IA**: recomendacoes auditaveis baseadas em score, historico e regras de negocio.

## Estado do Recorte Atual

Este workspace contem principalmente a infraestrutura da Central de Dados:

- upload XLSX para Supabase Storage;
- processamento server-side em fatias;
- staging auditavel;
- historico de importacoes;
- indicador de origem real/demonstracao;
- extensao Chrome para captura assistida do Aster;
- diagnosticos e evidencias de investigacao.

Ele nao contem todo o app final montado, rotas completas, `package.json`, estilos globais, componentes UI de base ou todas as Edge Functions historicas citadas nos documentos de referencia.

## Dependencias Ainda Fora Deste Recorte

- Projeto React/Vite completo onde os componentes serao integrados.
- Cliente Supabase em `@/lib/supabase/client`.
- Componentes UI e hooks usados pelos arquivos React.
- RPC `promover_importacao`.
- Edge Function de ingestao Aster, caso a extensao use `abr-collector-ingest`.
- Secrets e configuracoes reais de ambiente.
