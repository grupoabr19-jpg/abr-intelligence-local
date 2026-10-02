create table if not exists public.dim_colaborador (
  id_colaborador text primary key,
  nome_canonico text not null,
  nome_erp text not null unique,
  nome_kommo text,
  canal text not null check (canal in ('VAREJO', 'ATACADO', 'OUTROS')),
  funcao text not null,
  territorio text,
  vigencia_inicio date not null default date '2026-01-01',
  vigencia_fim date,
  ativo boolean not null default true,
  atualizado_em timestamptz not null default now()
);

alter table public.dim_colaborador add column if not exists id_colaborador text;
alter table public.dim_colaborador add column if not exists nome_canonico text;
alter table public.dim_colaborador add column if not exists nome_erp text;
alter table public.dim_colaborador add column if not exists nome_kommo text;
alter table public.dim_colaborador add column if not exists canal text;
alter table public.dim_colaborador add column if not exists funcao text;
alter table public.dim_colaborador add column if not exists territorio text;
alter table public.dim_colaborador add column if not exists vigencia_inicio date default date '2026-01-01';
alter table public.dim_colaborador add column if not exists vigencia_fim date;
alter table public.dim_colaborador add column if not exists ativo boolean default true;
alter table public.dim_colaborador add column if not exists atualizado_em timestamptz default now();

create unique index if not exists uq_dim_colaborador_nome_erp
  on public.dim_colaborador(nome_erp)
  where nome_erp is not null;

create index if not exists idx_dim_colaborador_canal
  on public.dim_colaborador(canal, funcao, territorio);

create table if not exists public.dim_ddd_atacado (
  ddd text not null,
  vendedor text not null,
  vigencia_inicio date not null default date '2026-01-01',
  vigencia_fim date,
  primary key (ddd, vendedor, vigencia_inicio)
);

alter table public.dim_colaborador enable row level security;
alter table public.dim_ddd_atacado enable row level security;

drop policy if exists dim_colaborador_auth_select on public.dim_colaborador;
create policy dim_colaborador_auth_select
  on public.dim_colaborador
  for select
  to authenticated
  using (true);

drop policy if exists dim_ddd_atacado_auth_select on public.dim_ddd_atacado;
create policy dim_ddd_atacado_auth_select
  on public.dim_ddd_atacado
  for select
  to authenticated
  using (true);

grant select on public.dim_colaborador to authenticated;
grant select on public.dim_ddd_atacado to authenticated;

insert into public.dim_colaborador(
  id_colaborador, nome_canonico, nome_erp, nome_kommo, canal, funcao, territorio
) values
  ('ATACADO_LARISSA_TERRA_ATF', 'LARISSA TERRA', 'ATF - LARISSA TERRA', 'LARISSA TERRA', 'ATACADO', 'VENDEDOR ATACADO', 'DDD 11, 12, 13'),
  ('ATACADO_LARISSA_TERRA_VARE', 'LARISSA TERRA', 'VARE - LARISSA TERRA', 'LARISSA TERRA', 'ATACADO', 'VENDEDOR ATACADO', 'DDD 11, 12, 13'),
  ('ATACADO_LARISSA_TERRA_VCORP', 'LARISSA TERRA', 'VCORP - LARISSA TERRA', 'LARISSA TERRA', 'ATACADO', 'VENDEDOR ATACADO', 'DDD 11, 12, 13'),
  ('ATACADO_JULIO_MELO_ATF', 'JULIO MELO', 'ATF - JULIO MELO', 'JULIO MELO', 'ATACADO', 'VENDEDOR ATACADO', 'DDD 15, 19'),
  ('ATACADO_WILSON_NETO_ATF', 'WILSON NETO', 'ATF - WILSON NETO', 'WILSON NETO', 'ATACADO', 'VENDEDOR ATACADO', 'DDD 14, 16, 17, 18'),

  ('VAREJO_BRUNA_PEREIRA', 'BRUNA', 'VARE - BRUNA PEREIRA', 'BRUNA', 'VAREJO', 'ESPECIALISTA', 'VARGINHA'),
  ('VAREJO_GABRIELA_CUNHA', 'GABRIELA', 'VARE - GABRIELA CUNHA', 'GABRIELA', 'VAREJO', 'ESPECIALISTA', 'ITAJUBA'),
  ('VAREJO_PAOLA_SANTOS', 'PAOLA', 'VARE - PAOLA SANTOS', 'PAOLA', 'VAREJO', 'VENDEDOR EXTERNO', 'POUSO ALEGRE'),
  ('VAREJO_RAFAELA_RESENDE', 'RAFAELA', 'VARE - RAFAELA RESENDE', 'RAFAELA', 'VAREJO', 'ESPECIALISTA', 'POUSO ALEGRE'),
  ('VAREJO_INAYARA_CUNHA', 'INAYARA', 'VARE - INAYARA CUNHA', 'INAYARA', 'VAREJO', 'ESPECIALISTA', 'EXTREMA'),
  ('VAREJO_JENNIFER_SILVA', 'JENNIFER', 'VARE - JENNIFER SILVA', 'JENNIFER', 'VAREJO', 'VENDEDOR EXTERNO', 'ITAJUBA'),
  ('VAREJO_JOSIANE_LIMA', 'JOSIANE FRAZAO', 'VARE - JOSIANE LIMA', 'JOSIANE FRAZAO', 'VAREJO', 'ESPECIALISTA', 'JUNDIAI'),
  ('VAREJO_LEIZ_TORSO', 'LEIZ', 'VARE - LEIZ TORSO', 'LEIZ', 'VAREJO', 'ESPECIALISTA', 'BRAGANCA'),
  ('VAREJO_MILENA_VAZ', 'MILENA', 'VARE - MILENA VAZ', 'MILENA', 'VAREJO', 'ESPECIALISTA', 'POCOS DE CALDAS'),
  ('VAREJO_GUSTAVO_ARAUJO', 'GUSTAVO', 'VARE - GUSTAVO ARAUJO', 'GUSTAVO', 'VAREJO', 'VENDEDOR EXTERNO', 'EXTREMA'),
  ('VAREJO_HELOA_LEITE', 'HELOA', 'VARE - HELOA LEITE', 'HELOA', 'VAREJO', 'CORPORATIVO', 'BRAGANCA'),
  ('VAREJO_DYOVANA_SILVA', 'DYOVANA', 'VARE - DYOVANA SILVA', 'DYOVANA', 'VAREJO', 'VENDEDOR EXTERNO', 'JUNDIAI'),
  ('VAREJO_EDMILA_MELO', 'EDMILA', 'VARE - EDMILA MELO', 'EDMILA', 'VAREJO', 'ESPECIALISTA', 'CAMBUI'),
  ('VAREJO_CAMILA_GUIMENTI', 'CAMILA GUIMENTI', 'VARE - CAMILA GUIMENTI', 'CAMILA GUIMENTI', 'VAREJO', 'CORPORATIVO', 'POCOS DE CALDAS'),
  ('VAREJO_ARIANE_SANTOS', 'ARIANE', 'VARE - ARIANE SANTOS', 'ARIANE', 'VAREJO', 'CONSTRUCAO CIVIL', 'CAMBUI'),

  ('VAREJO_VARC_ARIANE_SOUZA', 'ARIANE', 'VARC - ARIANE SOUZA', 'ARIANE', 'VAREJO', 'CONSTRUCAO CIVIL', 'CAMBUI'),
  ('VAREJO_VARC_EDMILA_EXTREMA', 'EDMILA', 'VARC - EDMILA MELO - EXTREMA', 'EDMILA', 'VAREJO', 'ESPECIALISTA', 'EXTREMA'),
  ('VAREJO_VARC_LEIZ_TORSO', 'LEIZ', 'VARC - LEIZ TORSO', 'LEIZ', 'VAREJO', 'ESPECIALISTA', 'BRAGANCA'),
  ('VAREJO_VARC_LEIZ_JUNDIAI', 'LEIZ', 'VARC - LEIZ TORSO - JUNDIAI', 'LEIZ', 'VAREJO', 'ESPECIALISTA', 'JUNDIAI'),

  ('VAREJO_VCORP_JESSICA_SANTOS', 'JESSICA.S', 'VCORP - JESSICA SANTOS', 'JESSICA.S', 'VAREJO', 'CORPORATIVO', 'ITAJUBA'),
  ('VAREJO_VCORP_CAMILA_GUIMENTI', 'CAMILA GUIMENTI', 'VCORP - CAMILA GUIMENTI', 'CAMILA GUIMENTI', 'VAREJO', 'CORPORATIVO', 'POCOS DE CALDAS'),
  ('VAREJO_VCORP_THAIS_OLIVEIRA', 'THAIS', 'VCORP - THAIS OLIVEIRA', 'THAIS', 'VAREJO', 'CORPORATIVO', 'VARGINHA'),
  ('VAREJO_VCORP_MATHEUS_TEIXEIRA', 'MATHEUS TEIXEIRA', 'VCORP - MATHEUS TEIXEIRA', 'MATHEUS TEIXEIRA', 'VAREJO', 'CORPORATIVO', 'CAMBUI'),
  ('VAREJO_VCORP_VITORIA_TAVARES', 'VITORIA', 'VCORP - VITORIA TAVARES', 'VITORIA', 'VAREJO', 'CORPORATIVO', 'POUSO ALEGRE'),
  ('VAREJO_VCORP_DYOVANA_JUNDIAI', 'KAYLANE', 'VCORP - DYOVANA SILVA - JUNDIAI', 'KAYLANE', 'VAREJO', 'CORPORATIVO', 'JUNDIAI'),
  ('VAREJO_VCORP_EDMILA_MELO', 'EDMILA', 'VCORP - EDMILA MELO', 'EDMILA', 'VAREJO', 'ESPECIALISTA', 'CAMBUI'),
  ('VAREJO_VCORP_HELOA_LEITE', 'HELOA', 'VCORP - HELOA LEITE', 'HELOA', 'VAREJO', 'CORPORATIVO', 'BRAGANCA'),
  ('VAREJO_VCORP_INAYARA_CUNHA', 'INAYARA', 'VCORP - INAYARA CUNHA', 'INAYARA', 'VAREJO', 'ESPECIALISTA', 'EXTREMA'),
  ('VAREJO_VCORP_KAYLANE_SILVA', 'KAYLANE', 'VCORP - KAYLANE SILVA', 'KAYLANE', 'VAREJO', 'CORPORATIVO', 'JUNDIAI'),
  ('VAREJO_VCORP_LEIZ_TORSO', 'LEIZ', 'VCORP - LEIZ TORSO', 'LEIZ', 'VAREJO', 'ESPECIALISTA', 'BRAGANCA'),
  ('VAREJO_VCORP_TAINARA_MATILDE', 'TAINARA', 'VCORP - TAINARA MATILDE', 'TAINARA', 'VAREJO', 'CORPORATIVO', 'EXTREMA')
on conflict (nome_erp) where nome_erp is not null do update set
  nome_canonico = excluded.nome_canonico,
  nome_kommo = excluded.nome_kommo,
  canal = excluded.canal,
  funcao = excluded.funcao,
  territorio = excluded.territorio,
  atualizado_em = now();

insert into public.dim_ddd_atacado(ddd, vendedor) values
  ('11', 'LARISSA TERRA'),
  ('12', 'LARISSA TERRA'),
  ('13', 'LARISSA TERRA'),
  ('15', 'JULIO MELO'),
  ('19', 'JULIO MELO'),
  ('14', 'WILSON NETO'),
  ('16', 'WILSON NETO'),
  ('17', 'WILSON NETO'),
  ('18', 'WILSON NETO')
on conflict (ddd, vendedor, vigencia_inicio) do nothing;
