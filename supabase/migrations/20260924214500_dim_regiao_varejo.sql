create table if not exists public.dim_regiao_varejo (
  colaborador text not null,
  funcao text not null,
  regiao_polo text not null,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  constraint dim_regiao_varejo_pkey primary key (colaborador, funcao),
  constraint dim_regiao_varejo_funcao_chk check (funcao in ('VENDEDOR EXTERNO', 'ESPECIALISTA', 'CORPORATIVO', 'CONSTRUÇÃO CIVIL')),
  constraint dim_regiao_varejo_regiao_chk check (regiao_polo in ('BRAGANÇA', 'JUNDIAÍ', 'VARGINHA', 'POUSO ALEGRE', 'POÇOS DE CALDAS', 'ITAJUBÁ', 'EXTREMA', 'CAMBUÍ'))
);

comment on table public.dim_regiao_varejo is
  'Cadastro fixo de praca/polo comercial por colaborador para rankings operacionais de atendimento. Nao usar municipio, cidade, CEP ou rota de cliente.';

comment on column public.dim_regiao_varejo.regiao_polo is
  'Praca/polo comercial atribuida ao colaborador para consolidacao de performance da equipe.';

insert into public.dim_regiao_varejo (colaborador, funcao, regiao_polo)
values
  ('ALESSANDRO', 'VENDEDOR EXTERNO', 'BRAGANÇA'),
  ('DYOVANA', 'VENDEDOR EXTERNO', 'JUNDIAÍ'),
  ('PETERSON', 'VENDEDOR EXTERNO', 'VARGINHA'),
  ('PAOLA', 'VENDEDOR EXTERNO', 'POUSO ALEGRE'),
  ('JOSÉ FELIPE', 'VENDEDOR EXTERNO', 'POÇOS DE CALDAS'),
  ('JENNIFER', 'VENDEDOR EXTERNO', 'ITAJUBÁ'),
  ('GUSTAVO', 'VENDEDOR EXTERNO', 'EXTREMA'),
  ('JULIANO', 'VENDEDOR EXTERNO', 'CAMBUÍ'),
  ('LEIZ', 'ESPECIALISTA', 'BRAGANÇA'),
  ('JOSIANE FRAZÃO', 'ESPECIALISTA', 'JUNDIAÍ'),
  ('BRUNA', 'ESPECIALISTA', 'VARGINHA'),
  ('RAFAELA', 'ESPECIALISTA', 'POUSO ALEGRE'),
  ('MILENA', 'ESPECIALISTA', 'POÇOS DE CALDAS'),
  ('GABRIELA', 'ESPECIALISTA', 'ITAJUBÁ'),
  ('INAYARA', 'ESPECIALISTA', 'EXTREMA'),
  ('EDMILA', 'ESPECIALISTA', 'CAMBUÍ'),
  ('HELOA', 'CORPORATIVO', 'BRAGANÇA'),
  ('KAYLANE', 'CORPORATIVO', 'JUNDIAÍ'),
  ('THAIS', 'CORPORATIVO', 'VARGINHA'),
  ('VITORIA', 'CORPORATIVO', 'POUSO ALEGRE'),
  ('CAMILA GUIMENTI', 'CORPORATIVO', 'POÇOS DE CALDAS'),
  ('JESSICA.S', 'CORPORATIVO', 'ITAJUBÁ'),
  ('TAINARA', 'CORPORATIVO', 'EXTREMA'),
  ('MATHEUS TEIXEIRA', 'CORPORATIVO', 'CAMBUÍ'),
  ('ARIANE', 'CONSTRUÇÃO CIVIL', 'CAMBUÍ')
on conflict (colaborador, funcao) do update
set regiao_polo = excluded.regiao_polo,
    atualizado_em = now();

create index if not exists idx_dim_regiao_varejo_regiao
  on public.dim_regiao_varejo (regiao_polo);

alter table public.dim_regiao_varejo enable row level security;

drop policy if exists "dim_regiao_varejo_auth_select" on public.dim_regiao_varejo;
create policy "dim_regiao_varejo_auth_select" on public.dim_regiao_varejo
  for select to authenticated
  using (true);
