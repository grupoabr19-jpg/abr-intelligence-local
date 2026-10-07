create table if not exists public.fato_cotacao_item (
  source_id text primary key,
  drive_file_id text not null,
  drive_file_name text,
  drive_modified_time timestamptz,
  sync_id text,
  row_number integer,
  data_cotacao date,
  numero_cotacao text,
  numero_esboco text,
  chave_esboco text,
  pedido_destino text,
  data_adicao_pv date,
  data_nf date,
  numero_nf text,
  status_original text,
  vendedor text,
  unidade text,
  cod_cliente text,
  cliente text,
  cidade text,
  uf text,
  tipo_frete text,
  item_pa text,
  desc_pa text,
  familia text,
  qtd_pedido numeric,
  peso_kg numeric,
  preco_kg numeric,
  valor_total numeric,
  data_entrega_comercial date,
  estoque_pa numeric,
  estoque_confirmado_pa numeric,
  payload_original jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_fato_cotacao_item_data on public.fato_cotacao_item(data_cotacao);
create index if not exists idx_fato_cotacao_item_file_modified on public.fato_cotacao_item(drive_file_id, drive_modified_time);
create index if not exists idx_fato_cotacao_item_status on public.fato_cotacao_item(status_original);
create index if not exists idx_fato_cotacao_item_familia on public.fato_cotacao_item(familia);

create table if not exists public.fato_estoque_disponivel (
  source_id text primary key,
  drive_file_id text not null,
  drive_file_name text,
  drive_modified_time timestamptz,
  sync_id text,
  row_number integer,
  familia text,
  subgrupo text,
  codigo text,
  descricao text,
  laminacao text,
  espessura text,
  estoque_disponivel_kg numeric,
  deposito text,
  nome_deposito text,
  payload_original jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_fato_estoque_disponivel_file_modified on public.fato_estoque_disponivel(drive_file_id, drive_modified_time);
create index if not exists idx_fato_estoque_disponivel_familia on public.fato_estoque_disponivel(familia);
create index if not exists idx_fato_estoque_disponivel_codigo on public.fato_estoque_disponivel(codigo);

create table if not exists public.fato_estoque_envelhecimento (
  source_id text primary key,
  drive_file_id text not null,
  drive_file_name text,
  drive_modified_time timestamptz,
  sync_id text,
  row_number integer,
  dt_base date,
  unidade text,
  cod_material text,
  familia text,
  desc_material text,
  deposito text,
  descricao_deposito text,
  aging text,
  quantidade_kg numeric,
  valor numeric,
  custo_medio_kg numeric,
  grupo text,
  tipo text,
  mercado text,
  payload_original jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_fato_estoque_envelhecimento_base on public.fato_estoque_envelhecimento(dt_base);
create index if not exists idx_fato_estoque_envelhecimento_file_modified on public.fato_estoque_envelhecimento(drive_file_id, drive_modified_time);
create index if not exists idx_fato_estoque_envelhecimento_familia on public.fato_estoque_envelhecimento(familia);
create index if not exists idx_fato_estoque_envelhecimento_aging on public.fato_estoque_envelhecimento(aging);

alter table public.fato_cotacao_item enable row level security;
alter table public.fato_estoque_disponivel enable row level security;
alter table public.fato_estoque_envelhecimento enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'fato_cotacao_item' and policyname = 'fato_cotacao_item_auth_select'
  ) then
    create policy fato_cotacao_item_auth_select on public.fato_cotacao_item for select to authenticated using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'fato_estoque_disponivel' and policyname = 'fato_estoque_disponivel_auth_select'
  ) then
    create policy fato_estoque_disponivel_auth_select on public.fato_estoque_disponivel for select to authenticated using (true);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and tablename = 'fato_estoque_envelhecimento' and policyname = 'fato_estoque_envelhecimento_auth_select'
  ) then
    create policy fato_estoque_envelhecimento_auth_select on public.fato_estoque_envelhecimento for select to authenticated using (true);
  end if;
end $$;
