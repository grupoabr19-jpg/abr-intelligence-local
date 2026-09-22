# Extensao ABR Intelligence - Captura Aster

Esta extensao e um fallback operacional para quando o Aster nao disponibiliza API oficial. Ela roda somente em `https://aster.gruposps.com.br/*`, observa respostas Fetch/XHR candidatas e envia arrays de objetos para uma URL de ingestao configurada pelo operador.

## Segurança

- A captura fica desligada por padrao.
- A extensao nao le senha, cookies, localStorage, arquivos ou respostas binarias.
- O operador precisa ativar manualmente a captura no popup.
- A chave do coletor deve ser curta, rotacionavel e tratada como segredo operacional.

## Instalacao

1. Abra `chrome://extensions`.
2. Ative o modo desenvolvedor.
3. Clique em **Carregar sem compactacao**.
4. Selecione a pasta `extension/aster-capture`.
5. Abra o popup da extensao.
6. Informe URL de ingestao, chave do coletor, UUID da fonte Aster e entidade.
7. Acesse o portal Aster, autentique normalmente e ative a captura apenas durante o relatorio desejado.

## Dependencia Externa

O popup sugere uma URL como `https://.../functions/v1/abr-collector-ingest`, mas essa Edge Function nao esta presente neste recorte organizado. A extensao aceita qualquer endpoint compativel que receba:

```json
{
  "fonte_id": "uuid",
  "sync_id": "ASTER-...",
  "entidade": "aster_relatorio",
  "rows": [],
  "metadata": {}
}
```
