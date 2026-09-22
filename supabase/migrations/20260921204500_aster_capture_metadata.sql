ALTER TABLE public.staging_dados
  ADD COLUMN IF NOT EXISTS coleta_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.staging_dados.coleta_metadata IS
  'Metadados não sensíveis da captura Aster, como endpoint lógico, módulo, método e status HTTP.';
