create table if not exists public.raw_obrasgov_project_summary (
  id bigserial primary key,
  ano_cadastro integer not null,
  uf text,
  situacao text,
  natureza_intervencao text,
  eixo text,
  projetos integer not null default 0,
  investimento_previsto numeric not null default 0,
  empregos_gerados numeric not null default 0,
  payload jsonb not null default '{}'::jsonb,
  coletado_em timestamptz not null default now()
);

create table if not exists public.fact_obrasgov_investments (
  id bigserial primary key,
  periodo_inicio date not null,
  uf text,
  situacao text,
  natureza_intervencao text,
  eixo text,
  projetos integer not null default 0,
  investimento_previsto numeric not null default 0,
  empregos_gerados numeric not null default 0,
  coletado_em timestamptz not null default now()
);

create unique index if not exists uq_raw_obrasgov_project_summary_grain
  on public.raw_obrasgov_project_summary (
    ano_cadastro,
    coalesce(uf, ''),
    coalesce(situacao, ''),
    coalesce(natureza_intervencao, ''),
    coalesce(eixo, '')
  );

create unique index if not exists uq_fact_obrasgov_investments_grain
  on public.fact_obrasgov_investments (
    periodo_inicio,
    coalesce(uf, ''),
    coalesce(situacao, ''),
    coalesce(natureza_intervencao, ''),
    coalesce(eixo, '')
  );

alter table public.raw_obrasgov_project_summary enable row level security;
alter table public.fact_obrasgov_investments enable row level security;

drop policy if exists raw_obrasgov_project_summary_read_public on public.raw_obrasgov_project_summary;
create policy raw_obrasgov_project_summary_read_public on public.raw_obrasgov_project_summary for select to anon, authenticated using (true);

drop policy if exists fact_obrasgov_investments_read_public on public.fact_obrasgov_investments;
create policy fact_obrasgov_investments_read_public on public.fact_obrasgov_investments for select to anon, authenticated using (true);

grant select on public.raw_obrasgov_project_summary to anon, authenticated;
grant select on public.fact_obrasgov_investments to anon, authenticated;

insert into public.mercado_fontes(source_key, nome, tipo, categoria, url_base, url_documentacao, frequencia, configuracao, observacoes)
values
  (
    'obrasgov_projetos',
    'ObrasGov projetos de investimento',
    'api',
    'governo',
    'https://api-publica.obrasgov.gestao.gov.br/obras',
    'https://api-publica.obrasgov.gestao.gov.br/obras/docs',
    'diaria',
    '{"env_base_url": "OBRASGOV_API_BASE_URL", "env_years": "OBRASGOV_YEARS", "env_page_size": "OBRASGOV_PAGE_SIZE", "env_max_pages": "OBRASGOV_MAX_PAGES"}'::jsonb,
    'API publica ObrasGov. Detalhe fica arquivado; Supabase recebe resumo por UF/situacao/natureza/eixo.'
  )
on conflict (source_key)
do update set
  nome = excluded.nome,
  tipo = excluded.tipo,
  categoria = excluded.categoria,
  url_base = excluded.url_base,
  url_documentacao = excluded.url_documentacao,
  frequencia = excluded.frequencia,
  configuracao = excluded.configuracao,
  observacoes = excluded.observacoes,
  atualizado_em = now();
