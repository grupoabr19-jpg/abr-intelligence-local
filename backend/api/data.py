from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

from backend.aster_collector.commercial_regions import classify_sale
from backend.aster_collector.data_requirements import EXTRACTION_RULES, REQUIREMENTS, requirements_by_source
from backend.aster_collector.external_sources import EXTERNAL_SPREADSHEET_SOURCES
from backend.aster_collector.report_registry import REPORTS
from backend.intelligence_domains import list_intelligence_domains
from tools.apply_migrations import connect_database, load_env
from tools.summarize_aster_sales_regions import parse_decimal


def list_reports() -> list[dict[str, Any]]:
    requirements_index = requirements_by_source()
    return [
        {
            "query_id": query_id,
            "area": report.area,
            "name": report.name,
            "entity": report.entity,
            "automation_status": report.automation_status,
            "deliverables": [item.key for item in requirements_index.get(query_id, ())],
            "notes": report.notes,
        }
        for query_id, report in sorted(REPORTS.items())
    ]


def list_requirements() -> dict[str, Any]:
    return {
        "requirements": [
            {
                "key": item.key,
                "title": item.title,
                "priority": item.priority,
                "refresh": item.refresh,
                "grain": item.grain,
                "objective": item.objective,
                "fields": list(item.fields),
                "known_sources": list(item.known_sources),
                "gaps": list(item.gaps),
            }
            for item in REQUIREMENTS
        ],
        "external_spreadsheet_sources": [
            {
                "key": item.key,
                "title": item.title,
                "folder_url": item.folder_url,
                "selection_rule": item.selection_rule,
                "latest_file_id": item.latest_file_id,
                "latest_file_name": item.latest_file_name,
                "latest_modified_time": item.latest_modified_time,
                "local_path": item.local_path,
                "likely_coverage": list(item.likely_coverage),
                "notes": item.notes,
            }
            for item in EXTERNAL_SPREADSHEET_SOURCES
        ],
        "extraction_rules": list(EXTRACTION_RULES),
    }


def list_domains() -> dict[str, Any]:
    return {"domains": list_intelligence_domains()}


def parse_payload_date(payload: dict[str, Any]) -> date | None:
    for key in (
        "DATA",
        "Data",
        "Data Venda",
        "Data Pedido",
        "Data Emissao",
        "Data Emissão",
        "Data Lcto",
        "Data Lancamento",
        "Data de Lançamento",
        "Data de Lancamento",
        "DocDate",
        "DATADE",
        "DATAATE",
    ):
        value = payload.get(key)
        if not value:
            continue
        text = str(value).strip()
        candidates = (
            (text, "%Y-%m-%dT%H:%M:%S.%fZ"),
            (text[:19], "%Y-%m-%dT%H:%M:%S"),
            (text[:10], "%Y-%m-%d"),
            (text[:10], "%d/%m/%Y"),
        )
        for candidate, fmt in candidates:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def in_date_range(value: date | None, date_from: date | None, date_to: date | None) -> bool:
    if value is None:
        return date_from is None and date_to is None
    if date_from and value < date_from:
        return False
    if date_to and value > date_to:
        return False
    return True


SALE_DATE_SQL = """
    case
      when payload_original->>'Data Venda' like '__/__/____'
        then make_date(
          substring(payload_original->>'Data Venda' from 7 for 4)::int,
          substring(payload_original->>'Data Venda' from 4 for 2)::int,
          substring(payload_original->>'Data Venda' from 1 for 2)::int
        )
      when payload_original->>'Data Venda' like '____-__-__%%'
        then left(payload_original->>'Data Venda', 10)::date
      else null
    end
"""


def money_sql(field_name: str) -> str:
    return f"""
        case
          when payload_original->>{field_name!r} is null or trim(payload_original->>{field_name!r}) = '' then 0::numeric
          when payload_original->>{field_name!r} like '%%,%%' then
            replace(
              replace(regexp_replace(payload_original->>{field_name!r}, '[^0-9,.-]', '', 'g'), '.', ''),
              ',',
              '.'
            )::numeric
          else regexp_replace(payload_original->>{field_name!r}, '[^0-9.-]', '', 'g')::numeric
        end
    """


def sales_where(date_from: date | None, date_to: date | None) -> tuple[str, list[Any]]:
    clauses = ["entidade = 'aster_report_d0a4d301'"]
    params: list[Any] = []
    if date_from:
        clauses.append(f"({SALE_DATE_SQL}) >= %s")
        params.append(date_from)
    if date_to:
        clauses.append(f"({SALE_DATE_SQL}) <= %s")
        params.append(date_to)
    return " and ".join(clauses), params


def sales_period_summary(date_from: date | None = None, date_to: date | None = None) -> dict[str, Any]:
    cached = read_sales_summary_cache(date_from=date_from, date_to=date_to)
    if cached:
        return cached
    return compute_sales_period_summary(
        date_from.isoformat() if date_from else "",
        date_to.isoformat() if date_to else "",
    )


def sales_summary_cache_key(date_from: date | None = None, date_to: date | None = None) -> str:
    return f"aster_report_d0a4d301:{date_from.isoformat() if date_from else 'all'}:{date_to.isoformat() if date_to else 'all'}"


def read_sales_summary_cache(date_from: date | None = None, date_to: date | None = None) -> dict[str, Any] | None:
    env = load_env()
    try:
        with connect_database(env) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select payload, refreshed_at
                    from public.dashboard_sales_summary_cache
                    where cache_key = %s
                    """,
                    (sales_summary_cache_key(date_from=date_from, date_to=date_to),),
                )
                row = cur.fetchone()
    except BaseException:
        return None
    if not row:
        return None
    payload, refreshed_at = row
    payload = dict(payload)
    payload["cache_refreshed_at"] = refreshed_at.isoformat() if refreshed_at else None
    return payload


def write_sales_summary_cache(date_from: date | None = None, date_to: date | None = None) -> dict[str, Any]:
    payload = compute_sales_period_summary(
        date_from.isoformat() if date_from else "",
        date_to.isoformat() if date_to else "",
    )
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.dashboard_sales_summary_cache(cache_key, date_from, date_to, payload, refreshed_at)
                values (%s, %s, %s, %s::jsonb, now())
                on conflict (cache_key)
                do update set
                  date_from = excluded.date_from,
                  date_to = excluded.date_to,
                  payload = excluded.payload,
                  refreshed_at = now()
                """,
                (
                    sales_summary_cache_key(date_from=date_from, date_to=date_to),
                    date_from,
                    date_to,
                    json.dumps(payload),
                ),
            )
            conn.commit()
    return payload


@lru_cache(maxsize=32)
def compute_sales_period_summary(date_from_text: str, date_to_text: str) -> dict[str, Any]:
    date_from = date.fromisoformat(date_from_text) if date_from_text else None
    date_to = date.fromisoformat(date_to_text) if date_to_text else None
    valor_total = money_sql("Valor Total")
    rec_liquida = money_sql("RecLiquida")
    lucro_bruto = money_sql("LucroBruto")
    margem_contribuicao = money_sql("Margem de Contribuição (MC)")
    peso_total = money_sql("Peso Total")
    date_filters: list[str] = []
    params: list[Any] = []
    if date_from:
        date_filters.append("sale_date >= %s")
        params.append(date_from)
    if date_to:
        date_filters.append("sale_date <= %s")
        params.append(date_to)
    sales_where_sql = f"where {' and '.join(date_filters)}" if date_filters else ""
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                with raw_sales as (
                    select
                      {SALE_DATE_SQL} as sale_date,
                      {valor_total} as valor_total,
                      {rec_liquida} as receita_liquida,
                      {lucro_bruto} as lucro_bruto,
                      {margem_contribuicao} as margem_contribuicao,
                      {peso_total} as peso_total,
                      nullif(payload_original->>'CodCliente', '') as cliente_codigo,
                      coalesce(
                        nullif(payload_original->>'Cliente', ''),
                        nullif(payload_original->>'Nome do cliente', ''),
                        nullif(payload_original->>'Nome Cliente', ''),
                        nullif(payload_original->>'CodCliente', ''),
                        'Sem cliente'
                      ) as cliente,
                      nullif(payload_original->>'Item', '') as item,
                      coalesce(
                        nullif(payload_original->>'Descrição', ''),
                        nullif(payload_original->>'Item', ''),
                        'Sem item'
                      ) as produto,
                      coalesce(nullif(payload_original->>'Familia', ''), 'Sem familia') as familia,
                      coalesce(nullif(payload_original->>'Segmento', ''), 'Sem segmento') as segmento,
                      coalesce(nullif(payload_original->>'Cidade', ''), 'Sem cidade') as cidade,
                      coalesce(nullif(payload_original->>'Estado', ''), 'Sem UF') as estado,
                      coalesce(nullif(payload_original->>'Vendedor', ''), 'Sem vendedor') as vendedor,
                      coalesce(nullif(payload_original->>'Tipo', ''), 'Sem tipo') as tipo,
                      coalesce(
                        nullif(payload_original->>'N° NF', ''),
                        nullif(payload_original->>'Nº NF', ''),
                        nullif(payload_original->>'NF', ''),
                        nullif(payload_original->>'Nota fiscal', ''),
                        nullif(payload_original->>'Nota Fiscal', '')
                      ) as nota_fiscal,
                      {money_sql("Valor Venda Perdida")} as valor_perdido
                    from public.staging_dados
                    where entidade = 'aster_report_d0a4d301'
                ),
                sales as materialized (
                    select *
                    from raw_sales
                    {sales_where_sql}
                )
                select
                  count(*)::int as linhas,
                  coalesce(sum(valor_total), 0) as valor_total,
                  coalesce(sum(receita_liquida), 0) as receita_liquida,
                  coalesce(sum(lucro_bruto), 0) as lucro_bruto,
                  coalesce(sum(peso_total), 0) as peso_total,
                  count(distinct cliente)::int as clientes,
                  count(distinct item)::int as itens,
                  min(sale_date) as data_min,
                  max(sale_date) as data_max,
                  (
                    select coalesce(jsonb_agg(to_jsonb(month_rows) order by month_rows.mes), '[]'::jsonb)
                    from (
                      select
                        to_char(date_trunc('month', sale_date), 'YYYY-MM') as mes,
                        count(*)::int as linhas,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(receita_liquida), 0) as receita_liquida,
                        coalesce(sum(lucro_bruto), 0) as lucro_bruto,
                        coalesce(sum(margem_contribuicao), 0) as margem_contribuicao,
                        coalesce(sum(peso_total), 0) as peso_total,
                        count(distinct nota_fiscal) filter (where nota_fiscal is not null)::int as notas_fiscais,
                        count(distinct cliente)::int as clientes,
                        coalesce(sum(valor_perdido), 0) as valor_perdido
                      from sales
                      where sale_date is not null
                      group by 1
                    ) month_rows
                  ) as monthly,
                  (
                    select coalesce(jsonb_agg(to_jsonb(family_rows) order by family_rows.peso_total desc), '[]'::jsonb)
                    from (
                      select
                        familia,
                        count(*)::int as linhas,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      group by 1
                      order by peso_total desc
                      limit 10
                    ) family_rows
                  ) as families,
                  (
                    select coalesce(jsonb_agg(to_jsonb(client_rows) order by client_rows.valor_total desc), '[]'::jsonb)
                    from (
                      select
                        cliente,
                        count(*)::int as linhas,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total,
                        max(sale_date) as ultima_compra
                      from sales
                      group by 1
                      order by valor_total desc
                      limit 20
                    ) client_rows
                  ) as clients_abc,
                  (
                    select coalesce(jsonb_agg(to_jsonb(drop_rows) order by drop_rows.queda_peso desc), '[]'::jsonb)
                    from (
                      with bounds as (
                        select date_trunc('month', max(sale_date))::date as latest_month
                        from sales
                        where sale_date is not null
                      ),
                      monthly_clients as (
                        select
                          s.cliente,
                          date_trunc('month', s.sale_date)::date as mes,
                          coalesce(sum(s.peso_total), 0) as peso_total
                        from sales s
                        where s.sale_date is not null
                        group by 1, 2
                      )
                      select
                        mc.cliente,
                        coalesce(sum(mc.peso_total) filter (where mc.mes = (select latest_month - interval '1 month' from bounds)), 0) as peso_anterior,
                        coalesce(sum(mc.peso_total) filter (where mc.mes = (select latest_month from bounds)), 0) as peso_atual,
                        coalesce(sum(mc.peso_total) filter (where mc.mes = (select latest_month - interval '1 month' from bounds)), 0)
                          - coalesce(sum(mc.peso_total) filter (where mc.mes = (select latest_month from bounds)), 0) as queda_peso
                      from monthly_clients mc
                      group by 1
                      having coalesce(sum(mc.peso_total) filter (where mc.mes = (select latest_month - interval '1 month' from bounds)), 0)
                          - coalesce(sum(mc.peso_total) filter (where mc.mes = (select latest_month from bounds)), 0) > 0
                      order by queda_peso desc
                      limit 20
                    ) drop_rows
                  ) as clients_decline,
                  (
                    select coalesce(jsonb_agg(to_jsonb(rfm_rows) order by rfm_rows.total desc), '[]'::jsonb)
                    from (
                      with client_rfm as (
                        select
                          cliente,
                          (select max(sale_date) from sales) - max(sale_date) as recencia_dias,
                          count(*)::int as frequencia,
                          coalesce(sum(valor_total), 0) as valor_total
                        from sales
                        where sale_date is not null
                        group by 1
                      )
                      select
                        case
                          when recencia_dias <= 30 and frequencia >= 8 then 'VIP'
                          when recencia_dias <= 60 and frequencia >= 4 then 'Recorrente'
                          when recencia_dias <= 90 then 'Promissor'
                          when recencia_dias <= 180 then 'Em risco'
                          else 'Dormindo'
                        end as segmento,
                        count(*)::int as total
                      from client_rfm
                      group by 1
                    ) rfm_rows
                  ) as rfm_segments,
                  (
                    select coalesce(jsonb_agg(to_jsonb(recency_rows) order by recency_rows.ordem), '[]'::jsonb)
                    from (
                      with client_last_purchase as (
                        select
                          cliente,
                          (select max(sale_date) from sales) - max(sale_date) as recencia_dias
                        from sales
                        where sale_date is not null
                        group by 1
                      )
                      select
                        case
                          when recencia_dias <= 30 then '0-30 dias'
                          when recencia_dias <= 60 then '31-60 dias'
                          when recencia_dias <= 90 then '61-90 dias'
                          when recencia_dias <= 180 then '91-180 dias'
                          else '+180 dias'
                        end as faixa,
                        case
                          when recencia_dias <= 30 then 1
                          when recencia_dias <= 60 then 2
                          when recencia_dias <= 90 then 3
                          when recencia_dias <= 180 then 4
                          else 5
                        end as ordem,
                        count(*)::int as clientes
                      from client_last_purchase
                      group by 1, 2
                    ) recency_rows
                  ) as recency_buckets,
                  (
                    select coalesce(jsonb_agg(to_jsonb(segment_rows) order by segment_rows.valor_total desc), '[]'::jsonb)
                    from (
                      select
                        segmento,
                        count(*)::int as linhas,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(receita_liquida), 0) as receita_liquida,
                        coalesce(sum(lucro_bruto), 0) as lucro_bruto,
                        coalesce(sum(margem_contribuicao), 0) as margem_contribuicao,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      group by 1
                      order by valor_total desc
                      limit 15
                    ) segment_rows
                  ) as segments,
                  (
                    select coalesce(jsonb_agg(to_jsonb(segment_month_rows) order by segment_month_rows.mes, segment_month_rows.segmento), '[]'::jsonb)
                    from (
                      select
                        to_char(date_trunc('month', sale_date), 'YYYY-MM') as mes,
                        segmento,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      where sale_date is not null
                      group by 1, 2
                    ) segment_month_rows
                  ) as segment_monthly,
                  (
                    select coalesce(jsonb_agg(to_jsonb(item_rows) order by item_rows.peso_total desc), '[]'::jsonb)
                    from (
                      select
                        produto,
                        item,
                        familia,
                        count(*)::int as linhas,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      group by 1, 2, 3
                      order by peso_total desc
                      limit 20
                    ) item_rows
                  ) as items,
                  (
                    select coalesce(jsonb_agg(to_jsonb(drop_rows) order by drop_rows.queda_peso desc), '[]'::jsonb)
                    from (
                      with bounds as (
                        select
                          case
                            when max(sale_date) >= (date_trunc('month', max(sale_date)) + interval '1 month - 1 day')::date
                              then date_trunc('month', max(sale_date))::date
                            else (date_trunc('month', max(sale_date)) - interval '1 month')::date
                          end as latest_month
                        from sales
                        where sale_date is not null
                      ),
                      monthly_items as (
                        select
                          produto,
                          date_trunc('month', sale_date)::date as mes,
                          coalesce(sum(peso_total), 0) as peso_total
                        from sales
                        where sale_date is not null
                        group by 1, 2
                      )
                      select
                        mi.produto,
                        coalesce(sum(mi.peso_total) filter (where mi.mes = (select latest_month - interval '1 month' from bounds)), 0) as peso_anterior,
                        coalesce(sum(mi.peso_total) filter (where mi.mes = (select latest_month from bounds)), 0) as peso_atual,
                        coalesce(sum(mi.peso_total) filter (where mi.mes = (select latest_month - interval '1 month' from bounds)), 0)
                          - coalesce(sum(mi.peso_total) filter (where mi.mes = (select latest_month from bounds)), 0) as queda_peso
                      from monthly_items mi
                      group by 1
                      having coalesce(sum(mi.peso_total) filter (where mi.mes = (select latest_month - interval '1 month' from bounds)), 0)
                          - coalesce(sum(mi.peso_total) filter (where mi.mes = (select latest_month from bounds)), 0) > 0
                      order by queda_peso desc
                      limit 20
                    ) drop_rows
                  ) as item_decline,
                  (
                    select coalesce(jsonb_agg(to_jsonb(family_segment_rows) order by family_segment_rows.peso_total desc), '[]'::jsonb)
                    from (
                      select
                        familia,
                        segmento,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      group by 1, 2
                      order by peso_total desc
                      limit 20
                    ) family_segment_rows
                  ) as family_segments,
                  (
                    select coalesce(jsonb_agg(to_jsonb(price_rows) order by price_rows.avg_preco_kg desc), '[]'::jsonb)
                    from (
                      select
                        familia,
                        percentile_cont(0.05) within group (order by valor_total / nullif(peso_total, 0)) as min_preco_kg,
                        sum(valor_total) / nullif(sum(peso_total), 0) as avg_preco_kg,
                        percentile_cont(0.95) within group (order by valor_total / nullif(peso_total, 0)) as max_preco_kg,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      where peso_total >= 10 and valor_total > 0
                      group by 1
                      order by avg_preco_kg desc
                      limit 15
                    ) price_rows
                  ) as price_stats,
                  (
                    select coalesce(jsonb_agg(to_jsonb(outlier_rows) order by abs(outlier_rows.desvio_pct) desc), '[]'::jsonb)
                    from (
                      with family_price as (
                        select
                          familia,
                          sum(valor_total) / nullif(sum(peso_total), 0) as media_familia_kg
                        from sales
                        where peso_total > 0 and valor_total > 0
                        group by 1
                      )
                      select
                        s.produto,
                        s.familia,
                        coalesce(sum(s.valor_total), 0) as valor_total,
                        coalesce(sum(s.peso_total), 0) as peso_total,
                        sum(s.valor_total) / nullif(sum(s.peso_total), 0) as preco_kg,
                        fp.media_familia_kg,
                        ((sum(s.valor_total) / nullif(sum(s.peso_total), 0)) - fp.media_familia_kg) / nullif(fp.media_familia_kg, 0) * 100 as desvio_pct
                      from sales s
                      join family_price fp on fp.familia = s.familia
                      where s.peso_total > 0 and s.valor_total > 0
                      group by 1, 2, fp.media_familia_kg
                      having sum(s.peso_total) >= 1000
                      order by abs(((sum(s.valor_total) / nullif(sum(s.peso_total), 0)) - fp.media_familia_kg) / nullif(fp.media_familia_kg, 0) * 100) desc
                      limit 20
                    ) outlier_rows
                  ) as price_outliers,
                  (
                    select coalesce(jsonb_agg(to_jsonb(price_month_rows) order by price_month_rows.mes), '[]'::jsonb)
                    from (
                      select
                        to_char(date_trunc('month', sale_date), 'YYYY-MM') as mes,
                        percentile_cont(0.05) within group (order by valor_total / nullif(peso_total, 0)) as min_preco_kg,
                        sum(valor_total) / nullif(sum(peso_total), 0) as avg_preco_kg,
                        percentile_cont(0.95) within group (order by valor_total / nullif(peso_total, 0)) as max_preco_kg,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      where sale_date is not null and peso_total >= 10 and valor_total > 0
                      group by 1
                    ) price_month_rows
                  ) as price_monthly,
                  (
                    select coalesce(jsonb_agg(to_jsonb(margin_rows) order by margin_rows.mes), '[]'::jsonb)
                    from (
                      select
                        to_char(date_trunc('month', sale_date), 'YYYY-MM') as mes,
                        coalesce(sum(receita_liquida), 0) as receita_liquida,
                        coalesce(sum(lucro_bruto), 0) as lucro_bruto,
                        coalesce(sum(margem_contribuicao), 0) as margem_contribuicao,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      where sale_date is not null
                      group by 1
                    ) margin_rows
                  ) as margin_monthly,
                  (
                    select coalesce(jsonb_agg(to_jsonb(margin_client_rows) order by margin_client_rows.margem_contribuicao desc), '[]'::jsonb)
                    from (
                      select
                        cliente,
                        coalesce(sum(receita_liquida), 0) as receita_liquida,
                        coalesce(sum(lucro_bruto), 0) as lucro_bruto,
                        coalesce(sum(margem_contribuicao), 0) as margem_contribuicao,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      group by 1
                      order by margem_contribuicao desc
                      limit 20
                    ) margin_client_rows
                  ) as margin_clients,
                  (
                    select coalesce(jsonb_agg(to_jsonb(loss_rows) order by loss_rows.valor_perdido desc), '[]'::jsonb)
                    from (
                      select
                        coalesce(nullif(trim(payload_original->>'Motivo 1'), ''), 'Sem motivo') as motivo,
                        count(*)::int as linhas,
                        coalesce(sum({money_sql("Valor Venda Perdida")}), 0) as valor_perdido
                      from public.staging_dados
                      where entidade = 'aster_report_d0a4d301'
                        and ({SALE_DATE_SQL}) is not null
                        {"and (" + SALE_DATE_SQL + ") >= %s" if date_from else ""}
                        {"and (" + SALE_DATE_SQL + ") <= %s" if date_to else ""}
                      group by 1
                      having coalesce(sum({money_sql("Valor Venda Perdida")}), 0) > 0
                      order by valor_perdido desc
                      limit 15
                    ) loss_rows
                  ) as losses,
                  (
                    select coalesce(jsonb_agg(to_jsonb(seller_rows) order by seller_rows.valor_total desc), '[]'::jsonb)
                    from (
                      select
                        vendedor,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(valor_perdido), 0) as valor_perdido,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      group by 1
                      order by valor_total desc
                      limit 20
                    ) seller_rows
                  ) as sellers,
                  (
                    select coalesce(jsonb_agg(to_jsonb(quote_month_rows) order by quote_month_rows.mes), '[]'::jsonb)
                    from (
                      select
                        to_char(date_trunc('month', sale_date), 'YYYY-MM') as mes,
                        coalesce(sum(peso_total) filter (where tipo = 'NFS'), 0) as kg_vendido,
                        coalesce(sum(peso_total) filter (where tipo = 'CPerd'), 0) as kg_perdido,
                        coalesce(sum(peso_total) filter (where tipo in ('NFS', 'CPerd')), 0) as kg_cotado,
                        coalesce(sum(valor_total) filter (where tipo = 'NFS'), 0) as valor_vendido,
                        coalesce(sum(valor_perdido) filter (where tipo = 'CPerd'), 0) as valor_perdido,
                        coalesce(sum(valor_total) filter (where tipo = 'NFS'), 0)
                          + coalesce(sum(valor_perdido) filter (where tipo = 'CPerd'), 0) as valor_cotado
                      from sales
                      where sale_date is not null
                      group by 1
                    ) quote_month_rows
                  ) as quote_monthly,
                  (
                    select coalesce(jsonb_agg(to_jsonb(quote_seller_rows) order by quote_seller_rows.kg_cotado desc), '[]'::jsonb)
                    from (
                      select
                        vendedor,
                        coalesce(sum(peso_total) filter (where tipo = 'NFS'), 0) as kg_vendido,
                        coalesce(sum(peso_total) filter (where tipo = 'CPerd'), 0) as kg_perdido,
                        coalesce(sum(peso_total) filter (where tipo in ('NFS', 'CPerd')), 0) as kg_cotado,
                        coalesce(sum(valor_total) filter (where tipo = 'NFS'), 0) as valor_vendido,
                        coalesce(sum(valor_perdido) filter (where tipo = 'CPerd'), 0) as valor_perdido
                      from sales
                      group by 1
                      having coalesce(sum(peso_total) filter (where tipo in ('NFS', 'CPerd')), 0) > 0
                      order by kg_cotado desc
                      limit 20
                    ) quote_seller_rows
                  ) as quote_sellers,
                  (
                    select coalesce(jsonb_agg(to_jsonb(funnel_rows) order by funnel_rows.ordem), '[]'::jsonb)
                    from (
                      select 1 as ordem, 'Cotado' as etapa, coalesce(sum(peso_total) filter (where tipo in ('NFS', 'CPerd')), 0) as kg_total
                      from sales
                      union all
                      select 2 as ordem, 'Vendido' as etapa, coalesce(sum(peso_total) filter (where tipo = 'NFS'), 0) as kg_total
                      from sales
                      union all
                      select 3 as ordem, 'Perdido' as etapa, coalesce(sum(peso_total) filter (where tipo = 'CPerd'), 0) as kg_total
                      from sales
                    ) funnel_rows
                  ) as quote_funnel,
                  (
                    select coalesce(jsonb_agg(to_jsonb(city_rows) order by city_rows.valor_total desc), '[]'::jsonb)
                    from (
                      select
                        cidade,
                        estado,
                        count(distinct cliente)::int as clientes,
                        coalesce(sum(valor_total), 0) as valor_total,
                        coalesce(sum(peso_total), 0) as peso_total
                      from sales
                      group by 1, 2
                      order by valor_total desc
                      limit 25
                    ) city_rows
                  ) as cities
                from sales
                """,
                params + params,
            )
            row = cur.fetchone() or (0, 0, 0, 0, 0, 0, 0, None, None, [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [])

    (
        linhas,
        total,
        liquida,
        lucro,
        peso,
        clientes,
        itens,
        min_date,
        max_date,
        monthly_rows,
        family_rows,
        client_rows,
        decline_rows,
        rfm_rows,
        recency_rows,
        segment_rows,
        segment_month_rows,
        item_rows,
        item_decline_rows,
        family_segment_rows,
        price_stat_rows,
        price_outlier_rows,
        price_month_rows,
        margin_monthly_rows,
        margin_client_rows,
        loss_rows,
        seller_rows,
        quote_month_rows,
        quote_seller_rows,
        quote_funnel_rows,
        city_rows,
    ) = row

    average_price_kg = Decimal("0")
    if peso:
        average_price_kg = total / peso

    monthly = [
        {
            "mes": item["mes"],
            "linhas": item["linhas"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
            "receita_liquida": f"{Decimal(str(item.get('receita_liquida', 0))):.2f}",
            "lucro_bruto": f"{Decimal(str(item.get('lucro_bruto', 0))):.2f}",
            "margem_contribuicao": f"{Decimal(str(item.get('margem_contribuicao', 0))):.2f}",
            "notas_fiscais": item.get("notas_fiscais", 0),
            "clientes": item.get("clientes", 0),
            "valor_perdido": f"{Decimal(str(item.get('valor_perdido', 0))):.2f}",
        }
        for item in monthly_rows
    ]
    families = [
        {
            "familia": item["familia"],
            "linhas": item["linhas"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in family_rows
    ]
    clients_abc = [
        {
            "cliente": item["cliente"],
            "linhas": item["linhas"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
            "ultima_compra": str(item["ultima_compra"]) if item.get("ultima_compra") else None,
        }
        for item in client_rows
    ]
    clients_decline = [
        {
            "cliente": item["cliente"],
            "peso_anterior": f"{Decimal(str(item['peso_anterior'])):.2f}",
            "peso_atual": f"{Decimal(str(item['peso_atual'])):.2f}",
            "queda_peso": f"{Decimal(str(item['queda_peso'])):.2f}",
        }
        for item in decline_rows
    ]
    segments = [
        {
            "segmento": item["segmento"],
            "linhas": item["linhas"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "receita_liquida": f"{Decimal(str(item['receita_liquida'])):.2f}",
            "lucro_bruto": f"{Decimal(str(item['lucro_bruto'])):.2f}",
            "margem_contribuicao": f"{Decimal(str(item['margem_contribuicao'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in segment_rows
    ]
    segment_monthly = [
        {
            "mes": item["mes"],
            "segmento": item["segmento"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in segment_month_rows
    ]
    items = [
        {
            "produto": item["produto"],
            "item": item.get("item"),
            "familia": item["familia"],
            "linhas": item["linhas"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in item_rows
    ]
    item_decline = [
        {
            "produto": item["produto"],
            "peso_anterior": f"{Decimal(str(item['peso_anterior'])):.2f}",
            "peso_atual": f"{Decimal(str(item['peso_atual'])):.2f}",
            "queda_peso": f"{Decimal(str(item['queda_peso'])):.2f}",
        }
        for item in item_decline_rows
    ]
    family_segments = [
        {
            "familia": item["familia"],
            "segmento": item["segmento"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in family_segment_rows
    ]
    price_stats = [
        {
            "familia": item["familia"],
            "min_preco_kg": f"{Decimal(str(item['min_preco_kg'] or 0)):.2f}",
            "avg_preco_kg": f"{Decimal(str(item['avg_preco_kg'] or 0)):.2f}",
            "max_preco_kg": f"{Decimal(str(item['max_preco_kg'] or 0)):.2f}",
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in price_stat_rows
    ]
    price_outliers = [
        {
            "produto": item["produto"],
            "familia": item["familia"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
            "preco_kg": f"{Decimal(str(item['preco_kg'] or 0)):.2f}",
            "media_familia_kg": f"{Decimal(str(item['media_familia_kg'] or 0)):.2f}",
            "desvio_pct": f"{Decimal(str(item['desvio_pct'] or 0)):.2f}",
        }
        for item in price_outlier_rows
    ]
    price_monthly = [
        {
            "mes": item["mes"],
            "min_preco_kg": f"{Decimal(str(item['min_preco_kg'] or 0)):.2f}",
            "avg_preco_kg": f"{Decimal(str(item['avg_preco_kg'] or 0)):.2f}",
            "max_preco_kg": f"{Decimal(str(item['max_preco_kg'] or 0)):.2f}",
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in price_month_rows
    ]
    margin_monthly = [
        {
            "mes": item["mes"],
            "receita_liquida": f"{Decimal(str(item['receita_liquida'])):.2f}",
            "lucro_bruto": f"{Decimal(str(item['lucro_bruto'])):.2f}",
            "margem_contribuicao": f"{Decimal(str(item['margem_contribuicao'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in margin_monthly_rows
    ]
    margin_clients = [
        {
            "cliente": item["cliente"],
            "receita_liquida": f"{Decimal(str(item['receita_liquida'])):.2f}",
            "lucro_bruto": f"{Decimal(str(item['lucro_bruto'])):.2f}",
            "margem_contribuicao": f"{Decimal(str(item['margem_contribuicao'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in margin_client_rows
    ]
    losses = [
        {
            "motivo": item["motivo"],
            "linhas": item["linhas"],
            "valor_perdido": f"{Decimal(str(item['valor_perdido'])):.2f}",
        }
        for item in loss_rows
    ]
    sellers = [
        {
            "vendedor": item["vendedor"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "valor_perdido": f"{Decimal(str(item['valor_perdido'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in seller_rows
    ]
    quote_monthly = [
        {
            "mes": item["mes"],
            "kg_cotado": f"{Decimal(str(item['kg_cotado'])):.2f}",
            "kg_vendido": f"{Decimal(str(item['kg_vendido'])):.2f}",
            "kg_perdido": f"{Decimal(str(item['kg_perdido'])):.2f}",
            "valor_cotado": f"{Decimal(str(item['valor_cotado'])):.2f}",
            "valor_vendido": f"{Decimal(str(item['valor_vendido'])):.2f}",
            "valor_perdido": f"{Decimal(str(item['valor_perdido'])):.2f}",
        }
        for item in quote_month_rows
    ]
    quote_sellers = [
        {
            "vendedor": item["vendedor"],
            "kg_cotado": f"{Decimal(str(item['kg_cotado'])):.2f}",
            "kg_vendido": f"{Decimal(str(item['kg_vendido'])):.2f}",
            "kg_perdido": f"{Decimal(str(item['kg_perdido'])):.2f}",
            "valor_vendido": f"{Decimal(str(item['valor_vendido'])):.2f}",
            "valor_perdido": f"{Decimal(str(item['valor_perdido'])):.2f}",
        }
        for item in quote_seller_rows
    ]
    quote_funnel = [
        {
            "etapa": item["etapa"],
            "kg_total": f"{Decimal(str(item['kg_total'])):.2f}",
        }
        for item in quote_funnel_rows
    ]
    cities = [
        {
            "cidade": item["cidade"],
            "estado": item["estado"],
            "clientes": item["clientes"],
            "valor_total": f"{Decimal(str(item['valor_total'])):.2f}",
            "peso_total": f"{Decimal(str(item['peso_total'])):.2f}",
        }
        for item in city_rows
    ]

    return {
        "linhas": linhas,
        "valor_total": f"{total:.2f}",
        "receita_liquida": f"{liquida:.2f}",
        "lucro_bruto": f"{lucro:.2f}",
        "peso_total": f"{peso:.2f}",
        "preco_medio_kg": f"{average_price_kg:.2f}",
        "clientes": clientes,
        "itens": itens,
        "data_min": min_date.isoformat() if min_date else None,
        "data_max": max_date.isoformat() if max_date else None,
        "monthly": monthly,
        "families": families,
        "clients_abc": clients_abc,
        "clients_decline": clients_decline,
        "rfm_segments": rfm_rows,
        "recency_buckets": recency_rows,
        "segments": segments,
        "segment_monthly": segment_monthly,
        "items": items,
        "item_decline": item_decline,
        "family_segments": family_segments,
        "price_stats": price_stats,
        "price_outliers": price_outliers,
        "price_monthly": price_monthly,
        "margin_monthly": margin_monthly,
        "margin_clients": margin_clients,
        "losses": losses,
        "sellers": sellers,
        "quote_monthly": quote_monthly,
        "quote_sellers": quote_sellers,
        "quote_funnel": quote_funnel,
        "cities": cities,
    }


def internal_dashboard_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    *,
    include_sales_regions: bool = False,
) -> dict[str, Any]:
    reports = list_reports()
    requirements = list_requirements()
    warnings: list[str] = []

    status_counts: dict[str, int] = defaultdict(int)
    area_counts: dict[str, int] = defaultdict(int)
    for report in reports:
        status_counts[report["automation_status"]] += 1
        area_counts[report["area"]] += 1

    requirement_rows = requirements["requirements"]
    covered_requirements = [item for item in requirement_rows if item["known_sources"]]
    gap_requirements = [item for item in requirement_rows if item["gaps"]]

    history: list[dict[str, Any]] = []
    staging_by_entity: list[dict[str, Any]] = []
    try:
        env = load_env()
        with connect_database(env) as conn:
            with conn.cursor() as cur:
                history_query = """
                    select entidade, sync_id, status, registros_lidos, registros_inseridos, iniciado_em
                    from public.historico_importacoes
                """
                history_params: list[Any] = []
                clauses = []
                if date_from:
                    clauses.append("iniciado_em::date >= %s")
                    history_params.append(date_from)
                if date_to:
                    clauses.append("iniciado_em::date <= %s")
                    history_params.append(date_to)
                if clauses:
                    history_query += " where " + " and ".join(clauses)
                history_query += " order by iniciado_em desc limit 12"
                cur.execute(history_query, history_params)
                history = [
                    {
                        "entidade": row[0],
                        "sync_id": row[1],
                        "status": row[2],
                        "registros_lidos": row[3],
                        "registros_inseridos": row[4],
                        "iniciado_em": row[5].isoformat() if row[5] else None,
                    }
                    for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    select entidade, count(*)::int
                    from public.staging_dados
                    group by entidade
                    order by count(*) desc
                    limit 12
                    """
                )
                staging_by_entity = [
                    {"entidade": row[0], "linhas": row[1]}
                    for row in cur.fetchall()
                ]
    except BaseException as exc:
        warnings.append(f"Banco indisponivel para resumo ao vivo: {type(exc).__name__}: {str(exc)[:160]}")

    regions: list[dict[str, Any]] = []
    sales_summary: dict[str, Any] = {}
    if include_sales_regions:
        try:
            regions = sales_regions_summary(date_from=date_from, date_to=date_to)
        except BaseException as exc:
            warnings.append(f"Resumo de regioes indisponivel: {type(exc).__name__}: {str(exc)[:160]}")
    try:
        sales_summary = sales_period_summary(date_from=date_from, date_to=date_to)
    except BaseException as exc:
        warnings.append(f"Resumo de vendas indisponivel: {type(exc).__name__}: {str(exc)[:160]}")

    return {
        "domain": "internal",
        "generated_from": "backend",
        "date_range": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
        "kpis": {
            "reports_total": len(reports),
            "reports_validated": status_counts.get("validated", 0),
            "reports_empty": status_counts.get("validated_empty", 0),
            "requirements_total": len(requirement_rows),
            "requirements_covered": len(covered_requirements),
            "requirements_with_gaps": len(gap_requirements),
            "spreadsheet_sources": len(requirements["external_spreadsheet_sources"]),
            "history_events": len(history),
        },
        "reports": reports,
        "reports_by_status": [{"status": key, "total": value} for key, value in sorted(status_counts.items())],
        "reports_by_area": [{"area": key, "total": value} for key, value in sorted(area_counts.items())],
        "requirements": requirement_rows,
        "external_spreadsheet_sources": requirements["external_spreadsheet_sources"],
        "staging_by_entity": staging_by_entity,
        "recent_history": history,
        "sales_summary": sales_summary,
        "sales_regions": regions,
        "warnings": warnings,
    }


def sales_regions_summary(date_from: date | None = None, date_to: date | None = None) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"linhas": 0, "valor_total": Decimal("0"), "criterios": defaultdict(int)}
    )
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            where_clauses = ["entidade = 'aster_report_d0a4d301'"]
            params: list[Any] = []
            parsed_sale_date = SALE_DATE_SQL
            if date_from:
                where_clauses.append(f"({parsed_sale_date}) >= %s")
                params.append(date_from)
            if date_to:
                where_clauses.append(f"({parsed_sale_date}) <= %s")
                params.append(date_to)
            cur.execute(
                f"""
                select
                  payload_original->>'Cidade' as cidade,
                  payload_original->>'Vendedor' as vendedor,
                  payload_original->>'Segmento' as segmento,
                  payload_original->>'Valor Total' as valor_total
                from public.staging_dados
                where {" and ".join(where_clauses)}
                """,
                params,
            )
            rows = cur.fetchall()

    for city, seller, segment, total_value in rows:
        classification = classify_sale(
            city=city,
            seller=seller,
            segment=segment,
        )
        key = (classification.canal, classification.regiao or "sem_regiao")
        groups[key]["linhas"] += 1
        groups[key]["valor_total"] += parse_decimal(total_value)
        groups[key]["criterios"][classification.criterio] += 1

    return [
        {
            "canal": canal,
            "regiao": regiao,
            "linhas": data["linhas"],
            "valor_total": f"{data['valor_total']:.2f}",
            "criterios": dict(data["criterios"]),
        }
        for (canal, regiao), data in sorted(groups.items())
    ]
