-- =====================================================================
-- Migration: Atualização explícita do limite do bucket 'imports' para 200MB
-- Garante que o bucket 'imports' em storage.buckets tenha file_size_limit de 209715200 (200 MB)
-- =====================================================================

UPDATE storage.buckets
SET file_size_limit = 209715200,
    allowed_mime_types = ARRAY[
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
      'application/octet-stream'
    ]
WHERE id = 'imports';

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'imports',
  'imports',
  false,
  209715200,
  ARRAY[
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'application/octet-stream'
  ]
)
ON CONFLICT (id) DO UPDATE SET
  file_size_limit = 209715200,
  allowed_mime_types = ARRAY[
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'application/octet-stream'
  ];
