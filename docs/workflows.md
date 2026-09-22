# Workflows Operacionais

## 1. Upload e Processamento XLSX

1. O operador seleciona uma planilha `.xlsx` na Central de Dados.
2. `CentralDadosService.calcularHashArquivo` calcula SHA-256 em blocos.
3. O sistema consulta `importacoes` para evitar upload duplicado.
4. Arquivo novo e enviado ao bucket privado `imports`.
5. Um registro e criado em `importacoes` com status `recebido`.
6. O frontend chama `processar-importacao` em modo de deteccao.
7. A Edge Function baixa o XLSX, identifica a melhor aba tabular, detecta tipo e amostra.
8. O operador confirma o tipo quando necessario.
9. O frontend chama a Edge Function em loop de fatias.
10. Cada fatia grava registros em `staging_dados`, atualiza checkpoint e historico.
11. Ao final, a importacao fica `aguardando_aprovacao`.

## 2. Promocao Para Base Real

1. O operador revisa resumo e amostras da staging.
2. `CentralDadosService.promoverImportacao` chama a RPC `promover_importacao`.
3. A RPC move dados validos para tabelas finais.
4. Duplicidades sao ignoradas ou contabilizadas conforme hash/chaves de negocio.
5. `DataOriginBadge` passa a indicar base real quando encontra dados nao demonstrativos.

## 3. Captura Assistida do Aster

1. O operador instala `extension/aster-capture` em modo desenvolvedor no Chrome.
2. No popup, informa URL de ingestao, chave do coletor, fonte Aster e entidade.
3. A captura permanece desligada ate o operador marcar a opcao de ativacao.
4. `content.js` injeta `page-hook.js` no contexto do portal.
5. `page-hook.js` observa Fetch/XHR da propria origem do Aster.
6. Respostas JSON ou endpoints com cara de API/relatorio sao enviadas ao service worker.
7. `background.js` procura o maior array de objetos no payload.
8. O lote e enviado para a funcao de ingestao configurada.
9. A staging recebe payloads com metadados nao sensiveis de origem.

## 3.1. Coletor Python do Aster

1. O worker Python carrega credenciais e endpoint de ingestao pelo `.env`.
2. Playwright abre `ASTER_BASE_URL` em Chromium.
3. O coletor autentica com usuario autorizado.
4. O listener de rede observa respostas JSON do dominio.
5. Quando encontra arrays de objetos, envia lotes ao endpoint configurado em `ABR_INGEST_URL`.
6. O operador/worker pode navegar ate relatorios especificos conforme os seletores forem confirmados.

Esse fluxo ainda precisa de seletores reais do Aster e dos relatorios-alvo. O esqueleto esta pronto, mas os campos de login e botoes devem ser confirmados numa sessao autorizada.

## 4. Origem dos Dados

1. `DataOriginBadge` consulta contagens reais nas tabelas principais.
2. Se nao houver dados, mostra base vazia.
3. Se houver apenas dados `source_system = demonstracao`, mostra demonstracao.
4. Se houver dados reais, mostra base real e a fonte principal.

## 5. Retomada Apos Falha

1. A tabela `importacoes` guarda `linha_checkpoint`.
2. Se a Edge Function falhar, o frontend tenta novamente com backoff.
3. Depois de tres falhas consecutivas, o operador pode retomar manualmente.
4. A proxima execucao continua a partir do checkpoint salvo.

## 6. Ordem Recomendada de Deploy

1. Aplicar migrations em `supabase/migrations`.
2. Criar/verificar bucket privado `imports`.
3. Publicar Edge Function `processar-importacao`.
4. Configurar secrets do Supabase.
5. Criar ambiente Python e instalar `requirements.txt`.
6. Rodar `playwright install chromium` no ambiente do worker.
7. Integrar `frontend/services` e `frontend/components` no app React principal.
8. Instalar a extensao Aster somente para operadores autorizados.
