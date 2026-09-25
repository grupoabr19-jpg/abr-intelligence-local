alter table public.atendimento_refresh_runs
  add column if not exists agregados_diarios integer not null default 0,
  add column if not exists agregados_colaboradores integer not null default 0,
  add column if not exists agregados_regioes integer not null default 0,
  add column if not exists eventos_resposta integer not null default 0;
