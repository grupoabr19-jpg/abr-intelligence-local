-- Persist the worksheet selected by the server-side XLSX detector.
ALTER TABLE public.importacoes
  ADD COLUMN IF NOT EXISTS sheet_path TEXT;

COMMENT ON COLUMN public.importacoes.sheet_path IS
  'ZIP entry of the worksheet selected for processing, for example xl/worksheets/sheet5.xml.';
