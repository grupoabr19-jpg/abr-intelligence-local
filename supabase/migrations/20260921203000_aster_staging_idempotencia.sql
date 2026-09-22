-- A ingestão Aster pode ser repetida quando a tela ou a rede falhar.
-- A coluna fonte_id é preenchida pelo coletor; o índice torna o retry seguro.
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_dados_fonte_hash
  ON public.staging_dados (fonte_id, hash_registro);
