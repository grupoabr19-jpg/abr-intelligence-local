from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from statistics import median
from typing import Any

from backend.aster_collector.commercial_regions import classify_sale
from backend.aster_collector.data_requirements import EXTRACTION_RULES, REQUIREMENTS, requirements_by_source
from backend.aster_collector.external_sources import EXTERNAL_SPREADSHEET_SOURCES
from backend.aster_collector.report_registry import REPORTS
from backend.intelligence_domains import list_intelligence_domains
from tools.apply_migrations import connect_crm_database, connect_database, load_env
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
                served_date_to = date_to
                if not row and date_from and date_to:
                    cur.execute(
                        """
                        select payload, refreshed_at, date_to
                        from public.dashboard_sales_summary_cache
                        where date_from = %s
                          and date_to <= %s
                        order by date_to desc nulls last, refreshed_at desc
                        limit 1
                        """,
                        (date_from, date_to),
                    )
                    fallback_row = cur.fetchone()
                    if fallback_row:
                        row = (fallback_row[0], fallback_row[1])
                        served_date_to = fallback_row[2]
    except BaseException:
        return None
    if not row:
        return None
    payload, refreshed_at = row
    payload = dict(payload)
    payload["cache_refreshed_at"] = refreshed_at.isoformat() if refreshed_at else None
    if served_date_to and served_date_to != date_to:
        payload["cache_served_date_to"] = served_date_to.isoformat()
        payload["cache_requested_date_to"] = date_to.isoformat() if date_to else None
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
                with sales as materialized (
                    select
                      sale_date,
                      valor_total,
                      receita_liquida,
                      lucro_bruto,
                      margem_contribuicao,
                      peso_total,
                      cliente_codigo,
                      cliente,
                      item,
                      produto,
                      familia,
                      segmento,
                      cidade,
                      estado,
                      vendedor,
                      tipo,
                      nota_fiscal,
                      valor_perdido,
                      motivo_perda
                    from public.dashboard_sales_fact
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
                        motivo_perda as motivo,
                        count(*)::int as linhas,
                        coalesce(sum(valor_perdido), 0) as valor_perdido
                      from sales
                      where sale_date is not null
                      group by 1
                      having coalesce(sum(valor_perdido), 0) > 0
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
                params,
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


def normalize_attendance_text(value: Any) -> str:
    text = str(value or "").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text)
    return text.upper()


def attendance_field(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized = {normalize_attendance_text(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(normalize_attendance_text(alias))
        if value not in (None, ""):
            return value
    return None


def parse_attendance_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    return None


def parse_attendance_number(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except Exception:
        return None


ATTENDANCE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "lead_id": ("ID do lead", "ID Lead", "Lead ID", "id", "ID"),
    "created_at": ("Criado em", "Data de criacao", "Data criação", "Created at"),
    "closed_at": ("Fechado em", "Data fechamento", "Closed at"),
    "situation": ("Situacao", "Situação", "Status", "Aberto/Fechado"),
    "pipeline": ("Funil", "Pipeline", "Funil original"),
    "stage": ("Etapa", "Etapa atual", "Status do lead", "Etapa original"),
    "status_id": ("Status ID", "ID Status", "status_id", "Kommo status id"),
    "first_contact": ("Primeiro contato recebido", "1o contato recebido", "Primeiro contato"),
    "first_response": ("Primeira acao humana", "Primeira resposta humana", "Primeira resposta"),
    "wait_minutes": ("Espera em minutos", "Tempo primeira acao", "Tempo primeira resposta", "Tempo de resposta"),
    "value": ("Valor", "Valor do lead", "Valor informado"),
    "next_task": ("Proxima tarefa", "Próxima tarefa", "Data proxima tarefa"),
    "last_interaction": ("Ultima interacao", "Última interação", "Ultima atividade"),
    "origin": ("Origem", "Origem do lead"),
    "region": ("Regiao", "Região"),
    "segment": ("Segmento",),
    "temperature": ("Temperatura",),
    "owner": ("Responsavel", "Responsável", "Responsavel atual", "Responsável atual"),
    "first_responder": ("Quem respondeu primeiro", "Primeiro respondente"),
    "link": ("Link Kommo", "Link", "URL"),
}

VAREJO_REGION_FALLBACK: tuple[tuple[str, str, str], ...] = (
    ("ALESSANDRO", "VENDEDOR EXTERNO", "BRAGANÇA"),
    ("DYOVANA", "VENDEDOR EXTERNO", "JUNDIAÍ"),
    ("PETERSON", "VENDEDOR EXTERNO", "VARGINHA"),
    ("PAOLA", "VENDEDOR EXTERNO", "POUSO ALEGRE"),
    ("JOSÉ FELIPE", "VENDEDOR EXTERNO", "POÇOS DE CALDAS"),
    ("JENNIFER", "VENDEDOR EXTERNO", "ITAJUBÁ"),
    ("GUSTAVO", "VENDEDOR EXTERNO", "EXTREMA"),
    ("JULIANO", "VENDEDOR EXTERNO", "CAMBUÍ"),
    ("LEIZ", "ESPECIALISTA", "BRAGANÇA"),
    ("JOSIANE FRAZÃO", "ESPECIALISTA", "JUNDIAÍ"),
    ("BRUNA", "ESPECIALISTA", "VARGINHA"),
    ("RAFAELA", "ESPECIALISTA", "POUSO ALEGRE"),
    ("MILENA", "ESPECIALISTA", "POÇOS DE CALDAS"),
    ("GABRIELA", "ESPECIALISTA", "ITAJUBÁ"),
    ("INAYARA", "ESPECIALISTA", "EXTREMA"),
    ("EDMILA", "ESPECIALISTA", "CAMBUÍ"),
    ("HELOA", "CORPORATIVO", "BRAGANÇA"),
    ("KAYLANE", "CORPORATIVO", "JUNDIAÍ"),
    ("THAIS", "CORPORATIVO", "VARGINHA"),
    ("VITORIA", "CORPORATIVO", "POUSO ALEGRE"),
    ("CAMILA GUIMENTI", "CORPORATIVO", "POÇOS DE CALDAS"),
    ("JESSICA.S", "CORPORATIVO", "ITAJUBÁ"),
    ("TAINARA", "CORPORATIVO", "EXTREMA"),
    ("MATHEUS TEIXEIRA", "CORPORATIVO", "CAMBUÍ"),
    ("ARIANE", "CONSTRUÇÃO CIVIL", "CAMBUÍ"),
    ("WILSON BUENO", "ATACADO", "ATACADO"),
    ("LARISSA", "ATACADO", "ATACADO"),
    ("JULIO", "ATACADO", "ATACADO"),
)

VAREJO_REGION_ALIASES: dict[str, str] = {
    "CAMILA": "CAMILA GUIMENTI",
    "HELOA LEITE": "HELOA",
    "JESSICA": "JESSICA.S",
    "JOSIANE": "JOSIANE FRAZAO",
    "THAIS OLIVEIRA": "THAIS",
    "WILSON": "WILSON BUENO",
    "WILSON NETO": "WILSON BUENO",
    "LARISSA TERRA": "LARISSA",
    "JULIO MELO": "JULIO",
}


def attendance_person_key(value: Any) -> str:
    normalized = normalize_attendance_text(value)
    official = VAREJO_REGION_ALIASES.get(normalized, normalized)
    return re.sub(r"[^A-Z0-9]", "", official)


def load_varejo_region_dimension(cur: Any) -> dict[str, dict[str, str]]:
    dimension = {
        attendance_person_key(colaborador): {
            "colaborador": colaborador,
            "funcao": funcao.title(),
            "regiao_polo": regiao,
        }
        for colaborador, funcao, regiao in VAREJO_REGION_FALLBACK
    }
    try:
        cur.execute(
            """
            select colaborador, funcao, regiao_polo
            from public.dim_regiao_varejo
            """
        )
        for colaborador, funcao, regiao in cur.fetchall():
            dimension[attendance_person_key(colaborador)] = {
                "colaborador": str(colaborador),
                "funcao": str(funcao).title(),
                "regiao_polo": str(regiao),
            }
    except Exception:
        cur.connection.rollback()
    return dimension


def new_attendance_metric() -> dict[str, Any]:
    return {
        "leads": set(),
        "ganhas": set(),
        "perdidas": set(),
        "sla_validos": set(),
        "sla_5": set(),
        "abertos": set(),
        "abertos_com_tarefa": set(),
        "pipeline_valores": {},
    }


def attendance_metric_row(metric: dict[str, Any]) -> dict[str, Any]:
    ganhas = len(metric["ganhas"])
    perdidas = len(metric["perdidas"])
    abertas = len(metric["abertos"])
    sla_validos = len(metric["sla_validos"])
    pipeline_valor = sum(metric["pipeline_valores"].values(), Decimal("0"))
    return {
        "leads": len(metric["leads"]),
        "ganhas": ganhas,
        "perdidas": perdidas,
        "win_rate": (ganhas / (ganhas + perdidas) * 100) if ganhas + perdidas else None,
        "sla_5_min": (len(metric["sla_5"]) / sla_validos * 100) if sla_validos else None,
        "pipeline_aberto_qtd": abertas,
        "pipeline_aberto_valor": f"{pipeline_valor:.2f}",
        "follow_up_cobertura": (len(metric["abertos_com_tarefa"]) / abertas * 100) if abertas else None,
    }


def attendance_summary_from_facts(date_from: date | None = None, date_to: date | None = None) -> dict[str, Any] | None:
    env = load_env()
    with connect_crm_database(env) as conn:
        with conn.cursor() as cur:
            try:
                query = """
                    select
                      f.lead_id,
                      f.created_at_kommo,
                      f.is_aberto,
                      f.is_ganho,
                      f.is_perdido,
                      f.valor,
                      coalesce(c.nome, 'Sem cadastro') as colaborador,
                      coalesce(c.funcao, 'Sem cadastro') as funcao,
                      coalesce(c.regiao_polo, 'Sem cadastro') as regiao_polo,
                      coalesce(p.nome, 'Sem funil') as funil,
                      coalesce(s.nome, 'Sem etapa') as etapa,
                      sla.espera_minutos,
                      sla.sla_valido,
                      sla.sla_5_min,
                      sla.sla_15_min,
                      sla.sem_resposta,
                      fo.tem_followup
                    from public.fato_atendimento_lead f
                    left join public.dim_atendimento_colaborador c on c.colaborador_key = f.colaborador_key
                    left join public.dim_kommo_pipeline p on p.pipeline_id = f.pipeline_id
                    left join public.dim_kommo_status s on s.status_id = f.status_id
                    left join public.fato_atendimento_sla sla on sla.lead_id = f.lead_id
                    left join public.fato_atendimento_followup fo on fo.lead_id = f.lead_id
                    where f.excluido = false
                """
                params: list[Any] = []
                if date_from:
                    query += " and (f.created_at_kommo is null or f.created_at_kommo::date >= %s)"
                    params.append(date_from)
                if date_to:
                    query += " and (f.created_at_kommo is null or f.created_at_kommo::date <= %s)"
                    params.append(date_to)
                cur.execute(query, params)
                rows = cur.fetchall()
                cur.execute(
                    """
                    select colaborador_key, nome, funcao, regiao_polo
                    from public.dim_atendimento_colaborador
                    where ativo = true
                    order by regiao_polo, funcao, nome
                    """
                )
                dimension_rows = [
                    {
                        "colaborador": row[1],
                        "funcao": row[2],
                        "regiao_polo": row[3],
                    }
                    for row in cur.fetchall()
                ]
                cur.execute(
                    """
                    select regra, severidade, total, checked_at
                    from public.atendimento_data_quality
                    order by checked_at desc
                    limit 20
                    """
                )
                quality_rows = [
                    {
                        "regra": row[0],
                        "severidade": row[1],
                        "total": row[2],
                        "checked_at": row[3].isoformat() if row[3] else None,
                    }
                    for row in cur.fetchall()
                ]
                cur.execute(
                    """
                    select finished_at
                    from public.atendimento_refresh_runs
                    where finished_at is not null
                    order by started_at desc
                    limit 1
                    """
                )
                latest_refresh_row = cur.fetchone()
                latest_refresh_at = latest_refresh_row[0].isoformat() if latest_refresh_row and latest_refresh_row[0] else None
                cur.execute(
                    """
                    select motivo_exclusao, count(*)
                    from public.fato_atendimento_lead
                    where excluido = true
                    group by motivo_exclusao
                    """
                )
                excluded_counts = {str(row[0] or ""): int(row[1] or 0) for row in cur.fetchall()}
                daily_query = """
                    select data_referencia, leads, abertos, ganhos, perdidos, pipeline_valor, sla_validos, sla_5, sla_15
                    from public.atendimento_agregado_diario
                """
                daily_params: list[Any] = []
                daily_clauses = []
                if date_from:
                    daily_clauses.append("data_referencia >= %s")
                    daily_params.append(date_from)
                if date_to:
                    daily_clauses.append("data_referencia <= %s")
                    daily_params.append(date_to)
                if daily_clauses:
                    daily_query += " where " + " and ".join(daily_clauses)
                daily_query += " order by data_referencia"
                cur.execute(daily_query, daily_params)
                daily_rows = [
                    {
                        "data": row[0].isoformat() if row[0] else None,
                        "leads": row[1],
                        "abertos": row[2],
                        "ganhos": row[3],
                        "perdidos": row[4],
                        "pipeline_valor": f"{Decimal(str(row[5] or 0)):.2f}",
                        "sla_validos": row[6],
                        "sla_5": row[7],
                        "sla_15": row[8],
                    }
                    for row in cur.fetchall()
                ]
                cur.execute(
                    """
                    select o.origem, count(*) as leads
                    from public.fato_atendimento_lead f
                    left join public.dim_atendimento_origem o on o.origem_key = f.origem_key
                    where f.excluido = false
                    group by o.origem
                    order by leads desc, o.origem
                    limit 12
                    """
                )
                origin_rows = [{"origem": row[0] or "Sem origem", "leads": row[1]} for row in cur.fetchall()]
                cur.execute(
                    """
                    select event_type, count(*)
                    from public.raw_kommo_events
                    where ativo = true
                    group by event_type
                    order by count(*) desc, event_type
                    limit 12
                    """
                )
                event_type_rows = [{"tipo": row[0] or "Sem tipo", "eventos": row[1]} for row in cur.fetchall()]
                cur.execute("select count(*) from public.raw_kommo_events where ativo = true")
                raw_events_count = int(cur.fetchone()[0] or 0)
                cur.execute("select count(*) from public.atendimento_evento_resposta")
                linked_events_count = int(cur.fetchone()[0] or 0)
                outcome_date_filter = []
                outcome_params: list[Any] = []
                created_date_filter = []
                created_params: list[Any] = []
                if date_from:
                    outcome_date_filter.append("f.closed_at_kommo::date >= %s")
                    outcome_params.append(date_from)
                    created_date_filter.append("(f.created_at_kommo is null or f.created_at_kommo::date >= %s)")
                    created_params.append(date_from)
                if date_to:
                    outcome_date_filter.append("f.closed_at_kommo::date <= %s")
                    outcome_params.append(date_to)
                    created_date_filter.append("(f.created_at_kommo is null or f.created_at_kommo::date <= %s)")
                    created_params.append(date_to)
                outcome_sql = " and " + " and ".join(outcome_date_filter) if outcome_date_filter else ""
                created_sql = " and " + " and ".join(created_date_filter) if created_date_filter else ""
                cur.execute(
                    f"""
                    select
                      coalesce(p.nome, 'Sem funil') as funil,
                      count(distinct f.lead_id) filter (where f.is_ganho and f.closed_at_kommo is not null {outcome_sql}) as ganhas,
                      count(distinct f.lead_id) filter (where f.is_perdido and f.closed_at_kommo is not null {outcome_sql}) as perdidas,
                      count(distinct f.lead_id) filter (where f.is_aberto {created_sql}) as abertos,
                      count(distinct f.lead_id) filter (where true {created_sql}) as leads_periodo
                    from public.fato_atendimento_lead f
                    left join public.dim_kommo_pipeline p on p.pipeline_id = f.pipeline_id
                    where f.excluido = false
                    group by coalesce(p.nome, 'Sem funil')
                    order by funil
                    """,
                    [*outcome_params, *outcome_params, *created_params, *created_params],
                )
                win_rate_funnel_rows = cur.fetchall()
            except Exception:
                cur.connection.rollback()
                return None

    if not rows:
        return None

    metric_global = new_attendance_metric()
    collaborator_metrics: dict[str, dict[str, Any]] = defaultdict(new_attendance_metric)
    collaborator_meta: dict[str, dict[str, str]] = {}
    region_metrics: dict[str, dict[str, Any]] = defaultdict(new_attendance_metric)
    response_waits: list[float] = []
    response_valid_count = 0
    fast_5_count = 0
    fast_15_count = 0
    no_response_count = 0
    no_followup_count = 0
    unmapped: set[str] = set()

    for row in rows:
        (
            lead_id,
            _created_at,
            is_aberto,
            is_ganho,
            is_perdido,
            valor,
            colaborador,
            funcao,
            regiao_polo,
            funil,
            _etapa,
            espera_minutos,
            sla_valido,
            sla_5_min,
            sla_15_min,
            sem_resposta,
            tem_followup,
        ) = row
        lead_id = str(lead_id)
        value = Decimal(str(valor or 0))
        collaborator_key = attendance_person_key(colaborador)
        if funcao == "Sem cadastro" or regiao_polo == "Sem cadastro":
            unmapped.add(str(colaborador))
        collaborator_meta[collaborator_key] = {
            "nome": colaborador,
            "funcao": funcao,
            "regiao_polo": regiao_polo,
        }
        targets = [metric_global, collaborator_metrics[collaborator_key], region_metrics[regiao_polo]]
        for metric in targets:
            metric["leads"].add(lead_id)
            if is_ganho:
                metric["ganhas"].add(lead_id)
            if is_perdido:
                metric["perdidas"].add(lead_id)
            if sla_valido:
                metric["sla_validos"].add(lead_id)
                if sla_5_min:
                    metric["sla_5"].add(lead_id)
            if is_aberto:
                metric["abertos"].add(lead_id)
                if tem_followup:
                    metric["abertos_com_tarefa"].add(lead_id)
                if value > 0:
                    metric["pipeline_valores"][lead_id] = value
        if sla_valido and espera_minutos is not None:
            wait_float = float(espera_minutos)
            response_waits.append(wait_float)
            response_valid_count += 1
            if sla_5_min:
                fast_5_count += 1
            if sla_15_min:
                fast_15_count += 1
        if sem_resposta:
            no_response_count += 1
        if is_aberto and not tem_followup:
            no_followup_count += 1

    global_row = attendance_metric_row(metric_global)
    ranking_colaboradores = []
    for collaborator_key, metric in collaborator_metrics.items():
        ranking_colaboradores.append({**collaborator_meta[collaborator_key], **attendance_metric_row(metric)})
    ranking_colaboradores.sort(key=lambda item: (item["ganhas"], item["win_rate"] or 0, item["leads"]), reverse=True)

    ranking_regioes = []
    for regiao, metric in region_metrics.items():
        integrantes = sorted(meta["nome"] for meta in collaborator_meta.values() if meta.get("regiao_polo") == regiao)
        ranking_regioes.append({"regiao_polo": regiao, "colaboradores": integrantes, **attendance_metric_row(metric)})
    ranking_regioes.sort(key=lambda item: (item["ganhas"], item["win_rate"] or 0, item["leads"]), reverse=True)

    win_rate_by_funnel = []
    for funil, wins, losses, abertos, leads_periodo in win_rate_funnel_rows:
        denominator = wins + losses
        win_rate_by_funnel.append(
            {
                "funil": funil,
                "ganhas": wins,
                "perdidas": losses,
                "fechadas": denominator,
                "abertas": abertos,
                "leads_periodo": leads_periodo,
                "conversion_rate": (wins / leads_periodo * 100) if leads_periodo else 0,
                "win_rate": (wins / denominator * 100) if denominator else 0,
            }
        )

    return {
        "data_available": True,
        "source_grain": "fato_atendimento",
        "rows": len(rows),
        "valid_rows": len(rows),
        "headers": [],
        "latest_imported_at": latest_refresh_at,
        "audit": {
            "qtd_excluida_comunicacao_interna": excluded_counts.get("interno", 0),
            "qtd_excluida_liderancas": excluded_counts.get("lideranca", 0),
        },
        "kpis": {
            "leads_novos": global_row["leads"],
            "leads_abertos": global_row["pipeline_aberto_qtd"],
            "tempo_mediano_primeira_resposta": median(response_waits) if response_waits else None,
            "sla_5_min": (fast_5_count / response_valid_count * 100) if response_valid_count else None,
            "sla_15_min": (fast_15_count / response_valid_count * 100) if response_valid_count else None,
            "taxa_nao_resposta": (no_response_count / len(rows) * 100) if rows else None,
            "pipeline_aberto_qtd": global_row["pipeline_aberto_qtd"],
            "pipeline_aberto_valor": global_row["pipeline_aberto_valor"],
            "leads_sem_proxima_tarefa": no_followup_count,
            "leads_sem_proxima_tarefa_pct": (no_followup_count / global_row["pipeline_aberto_qtd"] * 100)
            if global_row["pipeline_aberto_qtd"]
            else None,
        },
        "win_rate_by_funnel": win_rate_by_funnel,
        "ranking_basis": "fatos_atendimento_regiao_polo_por_colaborador",
        "region_dimension": dimension_rows,
        "ranking_colaboradores": ranking_colaboradores,
        "ranking_regioes": ranking_regioes,
        "unmapped_collaborators": sorted(unmapped),
        "data_quality": quality_rows,
        "daily": daily_rows,
        "origins": origin_rows,
        "event_types": event_type_rows,
        "event_stats": {
            "raw_events": raw_events_count,
            "linked_events": linked_events_count,
        },
    }


def attendance_summary(date_from: date | None = None, date_to: date | None = None) -> dict[str, Any]:
    fact_summary = attendance_summary_from_facts(date_from, date_to)
    if fact_summary:
        return fact_summary

    env = load_env()
    with connect_crm_database(env) as conn:
        with conn.cursor() as cur:
            region_dimension = load_varejo_region_dimension(cur)
            cur.execute(
                """
                select source_id, payload_original, imported_at
                from public.staging_dados
                where entidade = 'atendimento_kommo'
                  and source_system = 'KOMMO_API'
                  and ativo = true
                order by imported_at desc
                limit 50000
                """
            )
            rows = [{"source_id": row[0], "payload": row[1], "imported_at": row[2]} for row in cur.fetchall()]

    def source_order(item: dict[str, Any]) -> int:
        source_id = str(item.get("source_id") or "")
        try:
            return int(source_id.rsplit(":", 1)[-1])
        except ValueError:
            return 0

    ordered_rows = sorted(rows, key=source_order)
    payloads: list[dict[str, Any]] = [dict(item["payload"]) for item in ordered_rows if isinstance(item["payload"], dict)]
    headers = sorted({key for payload in payloads for key in payload.keys()})
    latest_import = max((item["imported_at"] for item in rows if item["imported_at"]), default=None)
    sample_rows = payloads[:5]
    region_dimension_rows = sorted(
        region_dimension.values(),
        key=lambda item: (item["regiao_polo"], item["funcao"], item["colaborador"]),
    )

    summary_rows = []
    if headers and len(headers) <= 3 and any("RELAT" in normalize_attendance_text(key) for key in headers):
        metric_key = next((key for key in headers if "RELAT" in normalize_attendance_text(key)), headers[0])
        value_key = next((key for key in headers if normalize_attendance_text(key) == "STATUS"), headers[-1])
        for payload in payloads:
            summary_rows.append({"metrica": payload.get(metric_key), "valor": payload.get(value_key)})

    missing_fields = [
        label
        for label, key in (
            ("ID do lead", "lead_id"),
            ("Criado em", "created_at"),
            ("Funil", "pipeline"),
            ("Etapa", "stage"),
            ("Situação", "situation"),
            ("Primeiro contato recebido", "first_contact"),
            ("Primeira acao humana", "first_response"),
            ("Espera em minutos", "wait_minutes"),
            ("Próxima tarefa", "next_task"),
        )
        if not any(attendance_field(payload, ATTENDANCE_FIELD_ALIASES[key]) is not None for payload in payloads)
    ]

    has_granular_leads = "ID do lead" not in missing_fields and len(payloads) > 0
    if not has_granular_leads:
        return {
            "data_available": False,
            "source_grain": "resumo" if summary_rows else "desconhecido",
            "rows": len(payloads),
            "headers": headers,
            "latest_imported_at": latest_import.isoformat() if latest_import else None,
            "summary_rows": summary_rows,
            "missing_required_fields": missing_fields,
            "audit": {
                "qtd_excluida_comunicacao_interna": 0,
                "qtd_excluida_liderancas": 0,
            },
            "ranking_basis": "regiao_polo_por_colaborador",
            "region_dimension": region_dimension_rows,
            "ranking_colaboradores": [],
            "ranking_regioes": [],
            "unmapped_collaborators": [],
            "message": "A planilha Kommo carregada ainda nao possui granularidade por lead para calcular SLA, funil, conversao e follow-up sem inventar metricas.",
        }

    valid: list[dict[str, Any]] = []
    excluded_internal: set[str] = set()
    excluded_leadership: set[str] = set()
    for payload in payloads:
        lead_id = str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["lead_id"]) or "").strip()
        if not lead_id:
            continue
        pipeline = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["pipeline"])
        stage = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["stage"])
        status_id = str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["status_id"]) or "").strip()
        normalized_pipeline = normalize_attendance_text(pipeline)
        normalized_stage = normalize_attendance_text(stage)
        if normalized_pipeline == "FUNIL DE LIDERANCAS":
            excluded_leadership.add(lead_id)
            continue
        if normalized_stage == "COMUNICACAO INTERNA" or status_id == "109439252":
            excluded_internal.add(lead_id)
            continue
        created_at = parse_attendance_datetime(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["created_at"]))
        if created_at and date_from and created_at.date() < date_from:
            continue
        if created_at and date_to and created_at.date() > date_to:
            continue
        valid.append(payload)

    lead_ids = {str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["lead_id"]) or "").strip() for payload in valid}
    open_leads = {
        str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["lead_id"]) or "").strip()
        for payload in valid
        if normalize_attendance_text(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["situation"])) == "ABERTO"
    }
    response_waits: list[float] = []
    response_leads: set[str] = set()
    fast_5: set[str] = set()
    fast_15: set[str] = set()
    contact_received: set[str] = set()
    no_response: set[str] = set()
    no_next_task: set[str] = set()
    pipeline_value = Decimal("0")
    wins_by_funnel: dict[str, int] = defaultdict(int)
    losses_by_funnel: dict[str, int] = defaultdict(int)
    collaborator_metrics: dict[str, dict[str, Any]] = defaultdict(new_attendance_metric)
    collaborator_meta: dict[str, dict[str, str]] = {}
    region_metrics: dict[str, dict[str, Any]] = defaultdict(new_attendance_metric)
    unmapped_collaborators: set[str] = set()

    for payload in valid:
        lead_id = str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["lead_id"]) or "").strip()
        first_contact = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["first_contact"])
        first_response = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["first_response"])
        wait = parse_attendance_number(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["wait_minutes"]))
        if first_contact:
            contact_received.add(lead_id)
        if first_contact and not first_response:
            no_response.add(lead_id)
        if first_contact and first_response and wait is not None and wait >= 0:
            wait_float = float(wait)
            response_waits.append(wait_float)
            response_leads.add(lead_id)
            if wait_float <= 5:
                fast_5.add(lead_id)
            if wait_float <= 15:
                fast_15.add(lead_id)
        if lead_id in open_leads:
            value = parse_attendance_number(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["value"]))
            if value and value > 0:
                pipeline_value += value
            if not attendance_field(payload, ATTENDANCE_FIELD_ALIASES["next_task"]):
                no_next_task.add(lead_id)
        stage = normalize_attendance_text(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["stage"]))
        funnel = str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["pipeline"]) or "Sem funil")
        if stage == "VENDA GANHA":
            wins_by_funnel[funnel] += 1
        elif stage == "VENDA PERDIDA":
            losses_by_funnel[funnel] += 1

        collaborator_name = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["owner"]) or attendance_field(
            payload, ATTENDANCE_FIELD_ALIASES["first_responder"]
        )
        collaborator_key = attendance_person_key(collaborator_name)
        if not collaborator_key:
            continue
        dimension_row = region_dimension.get(collaborator_key)
        if not dimension_row:
            unmapped_collaborators.add(str(collaborator_name).strip())
        collaborator_meta[collaborator_key] = {
            "nome": dimension_row["colaborador"] if dimension_row else str(collaborator_name).strip(),
            "funcao": dimension_row["funcao"] if dimension_row else "Sem cadastro",
            "regiao_polo": dimension_row["regiao_polo"] if dimension_row else "Sem cadastro",
        }
        metric_targets = [collaborator_metrics[collaborator_key]]
        if dimension_row:
            metric_targets.append(region_metrics[dimension_row["regiao_polo"]])
        value = parse_attendance_number(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["value"])) or Decimal("0")
        has_next_task = bool(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["next_task"]))
        for metric in metric_targets:
            metric["leads"].add(lead_id)
            if stage == "VENDA GANHA":
                metric["ganhas"].add(lead_id)
            elif stage == "VENDA PERDIDA":
                metric["perdidas"].add(lead_id)
            if first_contact and first_response and wait is not None and wait >= 0:
                metric["sla_validos"].add(lead_id)
                if float(wait) <= 5:
                    metric["sla_5"].add(lead_id)
            if lead_id in open_leads:
                metric["abertos"].add(lead_id)
                if has_next_task:
                    metric["abertos_com_tarefa"].add(lead_id)
                if value > 0:
                    metric["pipeline_valores"][lead_id] = value

    win_rate_by_funnel = []
    for funnel in sorted(set(wins_by_funnel) | set(losses_by_funnel)):
        wins = wins_by_funnel.get(funnel, 0)
        losses = losses_by_funnel.get(funnel, 0)
        denominator = wins + losses
        win_rate_by_funnel.append(
            {
                "funil": funnel,
                "ganhas": wins,
                "perdidas": losses,
                "win_rate": (wins / denominator * 100) if denominator else 0,
            }
        )

    ranking_colaboradores = []
    for collaborator_key, metric in collaborator_metrics.items():
        meta = collaborator_meta[collaborator_key]
        ranking_colaboradores.append({**meta, **attendance_metric_row(metric)})
    ranking_colaboradores.sort(key=lambda item: (item["ganhas"], item["win_rate"] or 0, item["leads"]), reverse=True)

    ranking_regioes = []
    for regiao, metric in region_metrics.items():
        integrantes = sorted(
            meta["nome"]
            for meta in collaborator_meta.values()
            if meta.get("regiao_polo") == regiao
        )
        ranking_regioes.append(
            {
                "regiao_polo": regiao,
                "colaboradores": integrantes,
                **attendance_metric_row(metric),
            }
        )
    ranking_regioes.sort(key=lambda item: (item["ganhas"], item["win_rate"] or 0, item["leads"]), reverse=True)

    return {
        "data_available": True,
        "source_grain": "lead",
        "rows": len(payloads),
        "valid_rows": len(valid),
        "headers": headers,
        "latest_imported_at": latest_import.isoformat() if latest_import else None,
        "sample_rows": sample_rows,
        "audit": {
            "qtd_excluida_comunicacao_interna": len(excluded_internal),
            "qtd_excluida_liderancas": len(excluded_leadership),
        },
        "kpis": {
            "leads_novos": len(lead_ids),
            "leads_abertos": len(open_leads),
            "tempo_mediano_primeira_resposta": median(response_waits) if response_waits else None,
            "sla_5_min": (len(fast_5) / len(response_leads) * 100) if response_leads else None,
            "sla_15_min": (len(fast_15) / len(response_leads) * 100) if response_leads else None,
            "taxa_nao_resposta": (len(no_response) / len(contact_received) * 100) if contact_received else None,
            "pipeline_aberto_qtd": len(open_leads),
            "pipeline_aberto_valor": f"{pipeline_value:.2f}",
            "leads_sem_proxima_tarefa": len(no_next_task),
            "leads_sem_proxima_tarefa_pct": (len(no_next_task) / len(open_leads) * 100) if open_leads else None,
        },
        "win_rate_by_funnel": win_rate_by_funnel,
        "ranking_basis": "regiao_polo_por_colaborador",
        "region_dimension": region_dimension_rows,
        "ranking_colaboradores": ranking_colaboradores,
        "ranking_regioes": ranking_regioes,
        "unmapped_collaborators": sorted(unmapped_collaborators),
    }


def market_decimal(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def add_months(value: date, months: int) -> date:
    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1
    return date(year, month, 1)


def market_timestamp(value: Any) -> str | None:
    return value.isoformat() if value else None


def market_registry_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        select
          source_key,
          source_name,
          category,
          status,
          configured,
          reachable,
          latest_reference_period,
          last_row_count,
          last_success_at,
          error_message,
          checked_at
        from public.market_source_registry
        order by
          case status
            when 'HEALTHY' then 1
            when 'CONFIGURED' then 2
            when 'ERROR' then 3
            else 4
          end,
          source_key
        """
    )
    return [
        {
            "source_key": row[0],
            "source_name": row[1],
            "category": row[2],
            "status": row[3],
            "configured": bool(row[4]),
            "reachable": bool(row[5]),
            "latest_reference_period": row[6],
            "last_row_count": row[7] or 0,
            "last_success_at": market_timestamp(row[8]),
            "error_message": row[9],
            "checked_at": market_timestamp(row[10]),
        }
        for row in cur.fetchall()
    ]


def market_filter_defaults(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        select tab_key, label, default_months, default_days, date_from, date_to, filters
        from public.market_tab_filter_defaults
        order by tab_key
        """
    )
    return {
        row[0]: {
            "label": row[1],
            "default_months": row[2],
            "default_days": row[3],
            "date_from": row[4].isoformat() if row[4] else None,
            "date_to": row[5].isoformat() if row[5] else None,
            "filters": row[6] or {},
        }
        for row in cur.fetchall()
    }


def market_decision_layer(cur: Any, date_to: date | None = None) -> dict[str, Any]:
    date_clause = "where periodo_inicio <= %s::date" if date_to else ""
    params: list[Any] = [date_to] if date_to else []

    cur.execute(
        f"""
        select periodo_inicio, family, classification, status, score, available_components_count, components, source_periods
        from public.agg_market_price_pressure
        {date_clause}
        order by periodo_inicio desc, family
        limit 16
        """,
        params,
    )
    price_pressure = [
        {
            "period": row[0].isoformat() if row[0] else None,
            "family": row[1],
            "classification": row[2],
            "status": row[3],
            "score": row[4],
            "available_components_count": row[5],
            "components": row[6] or {},
            "source_periods": row[7] or {},
        }
        for row in cur.fetchall()
    ]

    cur.execute(
        f"""
        select periodo_inicio, family, classification, status, score, available_components_count, drivers, source_periods
        from public.agg_market_demand_family
        {date_clause}
        order by periodo_inicio desc, family
        limit 16
        """,
        params,
    )
    demand = [
        {
            "period": row[0].isoformat() if row[0] else None,
            "family": row[1],
            "classification": row[2],
            "status": row[3],
            "score": row[4],
            "available_components_count": row[5],
            "drivers": row[6] or [],
            "source_periods": row[7] or {},
        }
        for row in cur.fetchall()
    ]

    cur.execute(
        f"""
        select periodo_inicio, signal_key, family, title, classification, score,
               available_components_count, drivers, target_tab, source_periods
        from public.agg_market_cockpit
        {date_clause}
        order by periodo_inicio desc, signal_key
        limit 20
        """,
        params,
    )
    cockpit = [
        {
            "period": row[0].isoformat() if row[0] else None,
            "signal_key": row[1],
            "family": row[2],
            "title": row[3],
            "classification": row[4],
            "score": row[5],
            "available_components_count": row[6],
            "drivers": row[7] or [],
            "target_tab": row[8],
            "source_periods": row[9] or {},
        }
        for row in cur.fetchall()
    ]

    cur.execute(
        f"""
        select periodo_inicio, polo, uf, opportunities, high_relevance, total_value,
               avg_relevance_score, product_matches
        from public.agg_market_opportunities
        {date_clause}
        order by periodo_inicio desc, high_relevance desc, opportunities desc
        limit 20
        """,
        params,
    )
    opportunities = [
        {
            "period": row[0].isoformat() if row[0] else None,
            "polo": row[1] or None,
            "uf": row[2] or None,
            "opportunities": row[3],
            "high_relevance": row[4],
            "total_value": market_decimal(row[5]),
            "avg_relevance_score": market_decimal(row[6]),
            "product_matches": row[7] or {},
        }
        for row in cur.fetchall()
    ]
    return {
        "price_pressure": price_pressure,
        "demand_family": demand,
        "cockpit": cockpit,
        "opportunities": opportunities,
    }


def market_latest_indicators(cur: Any, source_keys: list[str], limit: int = 12) -> list[dict[str, Any]]:
    if not source_keys:
        return []
    cur.execute(
        """
        select source_key, indicador_key, indicador_nome, periodo_label, geografia, unidade, valor
        from (
          select
            mi.source_key,
            mi.indicador_key,
            mi.indicador_nome,
            mi.periodo_label,
            mi.geografia,
            mi.unidade,
            mi.valor,
            row_number() over (
              partition by mi.source_key, mi.indicador_key, coalesce(mi.geografia, '')
              order by mi.periodo_inicio desc nulls last, mi.coletado_em desc
            ) as ordem
          from public.mercado_indicadores mi
          left join public.market_indicator_metadata mim
            on mim.source_key = mi.source_key
           and mim.indicator_key = mi.indicador_key
           and mim.active = true
          where mi.source_key = any(%s)
            and mi.valor is not null
            and (
              mim.source_key is null
              or (
                (mim.allow_zero or mi.valor <> 0)
                and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
                and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
              )
            )
        ) ranked
        where ordem = 1
        order by source_key, indicador_nome, geografia
        limit %s
        """,
        (source_keys, limit),
    )
    return [
        {
            "source_key": row[0],
            "indicator_key": row[1],
            "name": row[2],
            "period": row[3],
            "geography": row[4],
            "unit": row[5],
            "value": market_decimal(row[6]),
        }
        for row in cur.fetchall()
    ]


def market_indicator_series(cur: Any, source_key: str, indicator_key: str, limit: int = 24) -> list[dict[str, Any]]:
    cur.execute(
        """
        select mi.periodo_inicio, mi.periodo_label, avg(mi.valor) as valor
        from public.mercado_indicadores mi
        left join public.market_indicator_metadata mim
          on mim.source_key = mi.source_key
         and mim.indicator_key = mi.indicador_key
         and mim.active = true
        where mi.source_key = %s
          and mi.indicador_key = %s
          and mi.valor is not null
          and (
            mim.source_key is null
            or (
              (mim.allow_zero or mi.valor <> 0)
              and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
              and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
            )
          )
        group by mi.periodo_inicio, mi.periodo_label
        order by mi.periodo_inicio desc nulls last
        limit %s
        """,
        (source_key, indicator_key, limit),
    )
    rows = cur.fetchall()
    return [
        {
            "period": row[0].isoformat() if row[0] else None,
            "period_label": row[1],
            "value": market_decimal(row[2]),
        }
        for row in reversed(rows)
    ]


def market_indicator_series_between(
    cur: Any,
    source_key: str,
    indicator_key: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 36,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        select mi.periodo_inicio, mi.periodo_label, avg(mi.valor) as valor
        from public.mercado_indicadores mi
        left join public.market_indicator_metadata mim
          on mim.source_key = mi.source_key
         and mim.indicator_key = mi.indicador_key
         and mim.active = true
        where mi.source_key = %s
          and mi.indicador_key = %s
          and mi.valor is not null
          and (%s::date is null or mi.periodo_inicio >= %s::date)
          and (%s::date is null or mi.periodo_inicio <= %s::date)
          and (
            mim.source_key is null
            or (
              (mim.allow_zero or mi.valor <> 0)
              and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
              and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
            )
          )
        group by mi.periodo_inicio, mi.periodo_label
        order by mi.periodo_inicio desc nulls last
        limit %s
        """,
        (source_key, indicator_key, date_from, date_from, date_to, date_to, limit),
    )
    rows = cur.fetchall()
    return [
        {
            "period": row[0].isoformat() if row[0] else None,
            "period_label": row[1],
            "value": market_decimal(row[2]),
        }
        for row in reversed(rows)
    ]


def market_latest_indicator_before(
    cur: Any,
    source_key: str,
    indicator_key: str,
    date_to: date | None = None,
) -> dict[str, Any] | None:
    cur.execute(
        """
        select mi.source_key, mi.indicador_key, mi.indicador_nome, mi.periodo_inicio,
               mi.periodo_label, mi.geografia, mi.unidade, mi.valor
        from public.mercado_indicadores mi
        left join public.market_indicator_metadata mim
          on mim.source_key = mi.source_key
         and mim.indicator_key = mi.indicador_key
         and mim.active = true
        where mi.source_key = %s
          and mi.indicador_key = %s
          and mi.valor is not null
          and (%s::date is null or mi.periodo_inicio <= %s::date)
          and (
            mim.source_key is null
            or (
              (mim.allow_zero or mi.valor <> 0)
              and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
              and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
            )
          )
        order by mi.periodo_inicio desc nulls last, mi.coletado_em desc
        limit 1
        """,
        (source_key, indicator_key, date_to, date_to),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "source_key": row[0],
        "indicator_key": row[1],
        "name": row[2],
        "period": row[3],
        "period_iso": row[3].isoformat() if row[3] else None,
        "period_label": row[4],
        "geography": row[5],
        "unit": row[6],
        "value": row[7],
        "value_text": market_decimal(row[7]),
    }


def market_pct_change(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous == 0:
        return None
    return ((current / previous) - Decimal("1")) * Decimal("100")


def market_one_year_before(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def market_indicator_yoy(cur: Any, latest: dict[str, Any] | None) -> Decimal | None:
    if not latest or not latest.get("period") or latest.get("value") is None:
        return None
    previous_cutoff = market_one_year_before(latest["period"])
    previous = market_latest_indicator_before(cur, latest["source_key"], latest["indicator_key"], previous_cutoff)
    return market_pct_change(latest["value"], previous["value"] if previous else None)


def market_indicator_3m_change(cur: Any, latest: dict[str, Any] | None) -> Decimal | None:
    if not latest or not latest.get("period"):
        return None
    cur.execute(
        """
        with bounds as (
          select %s::date as cutoff
        ),
        current_window as (
          select avg(mi.valor) as valor
          from public.mercado_indicadores mi
          left join public.market_indicator_metadata mim
            on mim.source_key = mi.source_key
           and mim.indicator_key = mi.indicador_key
           and mim.active = true,
          bounds
          where mi.source_key = %s
            and mi.indicador_key = %s
            and mi.valor is not null
            and mi.periodo_inicio <= bounds.cutoff
            and mi.periodo_inicio > bounds.cutoff - interval '3 months'
            and (
              mim.source_key is null
              or (
                (mim.allow_zero or mi.valor <> 0)
                and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
                and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
              )
            )
        ),
        previous_window as (
          select avg(mi.valor) as valor
          from public.mercado_indicadores mi
          left join public.market_indicator_metadata mim
            on mim.source_key = mi.source_key
           and mim.indicator_key = mi.indicador_key
           and mim.active = true,
          bounds
          where mi.source_key = %s
            and mi.indicador_key = %s
            and mi.valor is not null
            and mi.periodo_inicio <= bounds.cutoff - interval '3 months'
            and mi.periodo_inicio > bounds.cutoff - interval '6 months'
            and (
              mim.source_key is null
              or (
                (mim.allow_zero or mi.valor <> 0)
                and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
                and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
              )
            )
        )
        select current_window.valor, previous_window.valor
        from current_window, previous_window
        """,
        (latest["period"], latest["source_key"], latest["indicator_key"], latest["source_key"], latest["indicator_key"]),
    )
    current_avg, previous_avg = cur.fetchone()
    return market_pct_change(current_avg, previous_avg)


def market_indicator_card(
    *,
    item_id: str,
    title: str,
    latest: dict[str, Any] | None,
    source_label: str,
    comparison_label: str,
    comparison_value: Decimal | None,
    target_tab: str,
    tooltip: str,
    unit_override: str | None = None,
) -> dict[str, Any] | None:
    if not latest or latest.get("value") is None:
        return None
    return {
        "id": item_id,
        "title": title,
        "value": market_decimal(latest["value"]),
        "unit": unit_override if unit_override is not None else latest.get("unit"),
        "comparison_label": comparison_label,
        "comparison_value": market_decimal(comparison_value),
        "source": source_label,
        "competence": latest.get("period_label") or latest.get("period_iso"),
        "target_tab": target_tab,
        "tooltip": tooltip,
    }


def market_signal(
    *,
    dimension: str,
    indicator: str,
    latest: dict[str, Any] | None,
    source_label: str,
    signal: str,
    change_3m: Decimal | None = None,
    yoy: Decimal | None = None,
    value_unit: str | None = None,
) -> dict[str, Any] | None:
    if not latest or latest.get("value") is None:
        return None
    return {
        "dimension": dimension,
        "indicator": indicator,
        "value": market_decimal(latest["value"]),
        "unit": value_unit if value_unit is not None else latest.get("unit"),
        "change_3m": market_decimal(change_3m),
        "yoy": market_decimal(yoy),
        "signal": signal,
        "source": source_label,
        "competence": latest.get("period_label") or latest.get("period_iso"),
    }


def market_overview_decision(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    indicators = {
        "ptax": ("bcb_dolar_ptax", "bcb_ptax_cotacaoVenda", "BCB"),
        "steel_consumption": ("aco_brasil_estatistica_mensal", "aco_brasil_consumo_aparente_total", "Aco Brasil"),
        "steel_domestic_sales": ("aco_brasil_estatistica_mensal", "aco_brasil_vendas_internas_total", "Aco Brasil"),
        "pim": ("ibge_pim_sidra", "ibge_pim_producao_fisica", "IBGE PIM"),
        "construction": ("ibge_construcao_sidra", "ibge_construcao_indice", "IBGE"),
        "cni_industry": ("cni_sondagem_industrial", "cni_industria_expectativa_demanda", "CNI Industria"),
        "cni_inputs": (
            "cni_sondagem_construcao",
            "cni_construcao_10_expectativa_de_compras_de_insumos_e_materias_primas_para_os_proximos_seis_meses",
            "CNI Construcao",
        ),
        "inda_sales": ("inda_estatisticas", "inda_vendas_variacao_mes_pct", "INDA"),
        "inda_stock": ("inda_estatisticas", "inda_estoque_variacao_mes_pct", "INDA"),
        "inda_purchases": ("inda_estatisticas", "inda_compras_variacao_mes_pct", "INDA"),
        "inda_imports": ("inda_estatisticas", "inda_importacao_variacao_mes_pct", "INDA"),
    }
    latest = {
        key: market_latest_indicator_before(cur, source_key, indicator_key, date_to)
        for key, (source_key, indicator_key, _source_label) in indicators.items()
    }
    yoy = {key: market_indicator_yoy(cur, value) for key, value in latest.items()}
    change_3m = {key: market_indicator_3m_change(cur, value) for key, value in latest.items()}

    ptax_30d: Decimal | None = None
    ptax = latest.get("ptax")
    if ptax and ptax.get("period"):
        cur.execute("select (%s::date - interval '30 days')::date", (ptax["period"],))
        ptax_previous_cutoff = cur.fetchone()[0]
        ptax_previous = market_latest_indicator_before(cur, "bcb_dolar_ptax", "bcb_ptax_cotacaoVenda", ptax_previous_cutoff)
        ptax_30d = market_pct_change(ptax["value"], ptax_previous["value"] if ptax_previous else None)

    cards = [
        market_indicator_card(
            item_id="ptax",
            title="PTAX venda",
            latest=ptax,
            source_label="BCB",
            comparison_label="30 dias",
            comparison_value=ptax_30d,
            target_tab="market-prices",
            tooltip="Dolar PTAX venda mais recente ate o corte. Formula: variacao contra a cotacao valida de aproximadamente 30 dias antes. Unidade: R$/US$.",
            unit_override="R$/US$",
        ),
        market_indicator_card(
            item_id="steel_consumption",
            title="Consumo aparente de aco",
            latest=latest.get("steel_consumption"),
            source_label="Aco Brasil",
            comparison_label="YoY",
            comparison_value=yoy.get("steel_consumption"),
            target_tab="steel-market",
            tooltip="Consumo aparente informado pelo Aco Brasil. Formula YoY: valor atual dividido pelo mesmo periodo do ano anterior menos 1. Unidade original da fonte.",
        ),
        market_indicator_card(
            item_id="pim",
            title="Atividade industrial",
            latest=latest.get("pim"),
            source_label="IBGE PIM",
            comparison_label="YoY",
            comparison_value=yoy.get("pim"),
            target_tab="industry",
            tooltip="Indice de producao fisica industrial disponivel no SIDRA. Formula YoY: valor atual dividido pelo mesmo periodo do ano anterior menos 1.",
        ),
        market_indicator_card(
            item_id="construction",
            title="Atividade da construcao",
            latest=latest.get("construction"),
            source_label="IBGE",
            comparison_label="YoY",
            comparison_value=yoy.get("construction"),
            target_tab="construction",
            tooltip="Indice da construcao no SIDRA. Formula YoY: valor atual dividido pelo mesmo periodo do ano anterior menos 1.",
        ),
        market_indicator_card(
            item_id="cni_industry",
            title="Expectativa demanda industrial",
            latest=latest.get("cni_industry"),
            source_label="CNI Industria",
            comparison_label="Distancia de 50",
            comparison_value=(latest["cni_industry"]["value"] - Decimal("50")) if latest.get("cni_industry") else None,
            target_tab="industry",
            tooltip="Indicador de expectativa de demanda da CNI. Valores acima de 50 indicam expectativa positiva; abaixo de 50 indicam retração.",
        ),
        market_indicator_card(
            item_id="cni_inputs",
            title="Compra de insumos construcao",
            latest=latest.get("cni_inputs"),
            source_label="CNI Construcao",
            comparison_label="Distancia de 50",
            comparison_value=(latest["cni_inputs"]["value"] - Decimal("50")) if latest.get("cni_inputs") else None,
            target_tab="construction",
            tooltip="Expectativa de compras de insumos e materias-primas na construcao. Base neutra: 50 pontos.",
        ),
        market_indicator_card(
            item_id="inda_sales",
            title="Distribuicao INDA",
            latest=latest.get("inda_sales"),
            source_label="INDA",
            comparison_label="Estoque MoM",
            comparison_value=latest["inda_stock"]["value"] if latest.get("inda_stock") else None,
            target_tab="steel-market",
            tooltip="Variacao mensal de vendas do INDA, acompanhada pela variacao mensal de estoque. Unidade: percentual ao mes.",
            unit_override="%",
        ),
    ]
    cards = [card for card in cards if card]

    def signal_for_change(value: Decimal | None, positive: str, negative: str, stable: str = "estavel") -> str:
        if value is None:
            return "sem comparativo"
        if value > Decimal("2"):
            return positive
        if value < Decimal("-2"):
            return negative
        return stable

    signals = [
        market_signal(
            dimension="Cambio",
            indicator="PTAX venda",
            latest=ptax,
            source_label="BCB",
            signal=signal_for_change(ptax_30d, "pressao externa maior", "pressao externa menor"),
            change_3m=change_3m.get("ptax"),
            yoy=yoy.get("ptax"),
            value_unit="R$/US$",
        ),
        market_signal(
            dimension="Mercado do aco",
            indicator="Consumo aparente",
            latest=latest.get("steel_consumption"),
            source_label="Aco Brasil",
            signal=signal_for_change(yoy.get("steel_consumption"), "acima do ano anterior", "abaixo do ano anterior"),
            change_3m=change_3m.get("steel_consumption"),
            yoy=yoy.get("steel_consumption"),
        ),
        market_signal(
            dimension="Industria",
            indicator="IBGE PIM",
            latest=latest.get("pim"),
            source_label="IBGE PIM",
            signal=signal_for_change(yoy.get("pim"), "fortalecimento", "enfraquecimento", "misto"),
            change_3m=change_3m.get("pim"),
            yoy=yoy.get("pim"),
        ),
        market_signal(
            dimension="Construcao",
            indicator="IBGE construcao",
            latest=latest.get("construction"),
            source_label="IBGE",
            signal=signal_for_change(yoy.get("construction"), "aceleracao", "recuo", "misto"),
            change_3m=change_3m.get("construction"),
            yoy=yoy.get("construction"),
        ),
        market_signal(
            dimension="Distribuicao",
            indicator="INDA vendas / estoque",
            latest=latest.get("inda_sales"),
            source_label="INDA",
            signal=(
                "estoque cresce com vendas em queda"
                if latest.get("inda_stock") and latest.get("inda_sales") and latest["inda_stock"]["value"] > 2 and latest["inda_sales"]["value"] < 0
                else "estoque cai com vendas em alta"
                if latest.get("inda_stock") and latest.get("inda_sales") and latest["inda_stock"]["value"] < 0 and latest["inda_sales"]["value"] > 0
                else "misto"
            ),
            change_3m=change_3m.get("inda_sales"),
            yoy=yoy.get("inda_sales"),
            value_unit="%",
        ),
    ]
    signals = [signal for signal in signals if signal]

    steel_series_keys = [
        ("consumo_aparente", "aco_brasil_estatistica_mensal", "aco_brasil_consumo_aparente_total"),
        ("vendas_internas", "aco_brasil_estatistica_mensal", "aco_brasil_vendas_internas_total"),
    ]
    steel_series_map: dict[str, dict[str, Any]] = {}
    for output_key, source_key, indicator_key in steel_series_keys:
        for point in market_indicator_series_between(cur, source_key, indicator_key, date_from=date_from, date_to=date_to, limit=24):
            period = point["period"]
            steel_series_map.setdefault(period, {"period": period, "period_label": point["period_label"]})[output_key] = point["value"]

    industry_series_map: dict[str, dict[str, Any]] = {}
    for point in market_indicator_series_between(cur, "ibge_pim_sidra", "ibge_pim_producao_fisica", date_from=date_from, date_to=date_to, limit=24):
        industry_series_map[point["period"]] = {
            "period": point["period"],
            "period_label": point["period_label"],
            "ibge_pim": point["value"],
        }

    construction_series_map: dict[str, dict[str, Any]] = {}
    construction_keys = [
        ("ibge_construcao", "ibge_construcao_sidra", "ibge_construcao_indice"),
        ("cni_compra_insumos", "cni_sondagem_construcao", indicators["cni_inputs"][1]),
    ]
    for output_key, source_key, indicator_key in construction_keys:
        for point in market_indicator_series_between(cur, source_key, indicator_key, date_from=date_from, date_to=date_to, limit=24):
            period = point["period"]
            construction_series_map.setdefault(period, {"period": period, "period_label": point["period_label"]})[output_key] = point["value"]

    distribution_bars = []
    for key, label in (
        ("inda_sales", "Vendas"),
        ("inda_purchases", "Compras"),
        ("inda_stock", "Estoque"),
        ("inda_imports", "Importacoes"),
    ):
        item = latest.get(key)
        if item and item.get("value") is not None:
            distribution_bars.append(
                {
                    "metric": label,
                    "value": market_decimal(item["value"]),
                    "period": item.get("period_iso"),
                    "period_label": item.get("period_label"),
                }
            )

    readings: list[dict[str, str]] = []
    if yoy.get("pim") is not None and latest.get("cni_industry"):
        cni_value = latest["cni_industry"]["value"]
        if yoy["pim"] > Decimal("2") and cni_value > Decimal("52"):
            readings.append({"key": "industry", "text": "Industria sinaliza fortalecimento: PIM cresce no ano e expectativa CNI esta acima de 52.", "severity": "positive"})
        elif yoy["pim"] < 0 and cni_value < Decimal("50"):
            readings.append({"key": "industry", "text": "Industria sinaliza enfraquecimento: PIM recua no ano e expectativa CNI esta abaixo de 50.", "severity": "attention"})
        else:
            readings.append({"key": "industry", "text": "Industria esta mista: atividade realizada e expectativa nao apontam na mesma direcao.", "severity": "neutral"})
    if yoy.get("construction") is not None and latest.get("cni_inputs") and yoy["construction"] > Decimal("2") and latest["cni_inputs"]["value"] > Decimal("52"):
        readings.append({"key": "construction", "text": "Construcao mostra aceleracao: indice setorial cresce no ano e expectativa de compra de insumos supera 52.", "severity": "positive"})
    if latest.get("inda_stock") and latest.get("inda_sales"):
        stock = latest["inda_stock"]["value"]
        sales = latest["inda_sales"]["value"]
        if stock > Decimal("2") and sales < 0:
            readings.append({"key": "distribution", "text": "Distribuicao com estoque crescendo enquanto vendas caem, sinal de maior folga no canal.", "severity": "attention"})
        elif stock < 0 and sales > 0:
            readings.append({"key": "distribution", "text": "Distribuicao com estoque em reducao e vendas em alta, sinal de giro mais forte no canal.", "severity": "positive"})
    if ptax_30d is not None:
        if ptax_30d > Decimal("2"):
            readings.append({"key": "fx", "text": "Cambio subiu mais de 2% em 30 dias, aumentando a pressao externa sobre itens importados.", "severity": "attention"})
        elif ptax_30d < Decimal("-2"):
            readings.append({"key": "fx", "text": "Cambio caiu mais de 2% em 30 dias, reduzindo a pressao externa sobre itens importados.", "severity": "positive"})
    if yoy.get("steel_consumption") is not None and yoy["steel_consumption"] > Decimal("3"):
        readings.append({"key": "steel", "text": "Consumo aparente de aco esta acima do mesmo periodo do ano anterior.", "severity": "positive"})

    return {
        "date_range": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
        "kpis": cards[:8],
        "signals": signals,
        "charts": {
            "steel": [steel_series_map[key] for key in sorted(steel_series_map) if key],
            "industry": [industry_series_map[key] for key in sorted(industry_series_map) if key],
            "construction": [construction_series_map[key] for key in sorted(construction_series_map) if key],
            "distribution": distribution_bars,
        },
        "decision_readings": readings[:5],
    }


INDUSTRY_DRIVER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "produtos_metal": {
        "label": "Produtos de Metal",
        "source_key": "ibge_pim_sidra",
        "indicator_key": "ibge_pim_producao_fisica",
        "classification_code": "129334",
        "kind": "yoy",
        "source": "IBGE PIM",
    },
    "maquinas": {
        "label": "Maquinas e Equipamentos",
        "source_key": "ibge_pim_sidra",
        "indicator_key": "ibge_pim_producao_fisica",
        "classification_code": "129337",
        "kind": "yoy",
        "source": "IBGE PIM",
    },
    "metalurgia": {
        "label": "Metalurgia",
        "source_key": "ibge_pim_sidra",
        "indicator_key": "ibge_pim_producao_fisica",
        "classification_code": "129333",
        "kind": "yoy",
        "source": "IBGE PIM",
    },
    "construcao_ibge": {
        "label": "Construcao",
        "source_key": "ibge_construcao_sidra",
        "indicator_key": "ibge_construcao_indice",
        "kind": "yoy",
        "source": "IBGE",
    },
    "cni_demanda": {
        "label": "CNI Demanda",
        "source_key": "cni_sondagem_industrial",
        "indicator_key": "cni_industria_expectativa_demanda",
        "kind": "cni50",
        "source": "CNI Industria",
    },
    "cni_compras": {
        "label": "CNI Compras",
        "source_key": "cni_sondagem_industrial",
        "indicator_key": "cni_industria_expectativa_compras",
        "kind": "cni50",
        "source": "CNI Industria",
    },
    "cni_construcao_atividade": {
        "label": "CNI Construcao",
        "source_key": "cni_sondagem_construcao",
        "indicator_key": "cni_construcao_9_expectativa_do_nivel_de_atividade_para_os_proximos_seis_meses",
        "kind": "cni50",
        "source": "CNI Construcao",
    },
    "cni_construcao_insumos": {
        "label": "CNI Insumos",
        "source_key": "cni_sondagem_construcao",
        "indicator_key": "cni_construcao_10_expectativa_de_compras_de_insumos_e_materias_primas_para_os_proximos_seis_meses",
        "kind": "cni50",
        "source": "CNI Construcao",
    },
    "cni_construcao_empreendimentos": {
        "label": "Novos Empreend.",
        "source_key": "cni_sondagem_construcao",
        "indicator_key": "cni_construcao_11_expectativa_de_novos_empreendimentos_e_servicos_para_os_proximos_seis_meses",
        "kind": "cni50",
        "source": "CNI Construcao",
    },
}


INDUSTRY_FAMILY_WEIGHTS: dict[str, dict[str, Decimal]] = {
    "CHAPAS": {
        "produtos_metal": Decimal("0.25"),
        "maquinas": Decimal("0.20"),
        "cni_demanda": Decimal("0.20"),
        "cni_compras": Decimal("0.15"),
        "metalurgia": Decimal("0.10"),
        "cni_construcao_insumos": Decimal("0.10"),
    },
    "TUBOS / METALONS": {
        "produtos_metal": Decimal("0.20"),
        "maquinas": Decimal("0.15"),
        "cni_demanda": Decimal("0.15"),
        "cni_compras": Decimal("0.15"),
        "construcao_ibge": Decimal("0.15"),
        "cni_construcao_insumos": Decimal("0.20"),
    },
    "PERFIS": {
        "construcao_ibge": Decimal("0.25"),
        "cni_construcao_empreendimentos": Decimal("0.20"),
        "cni_construcao_insumos": Decimal("0.20"),
        "produtos_metal": Decimal("0.15"),
        "cni_construcao_atividade": Decimal("0.15"),
        "maquinas": Decimal("0.05"),
    },
    "TELHAS": {
        "cni_construcao_atividade": Decimal("0.25"),
        "cni_construcao_empreendimentos": Decimal("0.20"),
        "cni_construcao_insumos": Decimal("0.20"),
        "construcao_ibge": Decimal("0.20"),
        "produtos_metal": Decimal("0.10"),
        "metalurgia": Decimal("0.05"),
    },
}


def market_normalize_cni_value(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value > Decimal("100"):
        return value / Decimal("10")
    return value


def market_driver_signal(kind: str, value: Decimal | None, yoy: Decimal | None) -> int | None:
    if kind == "cni50":
        normalized = market_normalize_cni_value(value)
        if normalized is None:
            return None
        if normalized > Decimal("52"):
            return 1
        if normalized < Decimal("48"):
            return -1
        return 0
    if yoy is None:
        return None
    if yoy > Decimal("2"):
        return 1
    if yoy < Decimal("-2"):
        return -1
    return 0


def market_demand_classification(index: Decimal | None) -> str:
    if index is None:
        return "SEM DADOS"
    if index >= Decimal("30"):
        return "ACELERANDO"
    if index >= Decimal("10"):
        return "LEVE ACELERACAO"
    if index > Decimal("-10"):
        return "ESTAVEL / MISTO"
    if index > Decimal("-30"):
        return "LEVE DESACELERACAO"
    return "DESACELERANDO"


def market_latest_indicator_dimension_before(
    cur: Any,
    *,
    source_key: str,
    indicator_key: str,
    date_to: date | None = None,
    classification_code: str | None = None,
) -> dict[str, Any] | None:
    cur.execute(
        """
        select mi.source_key, mi.indicador_key, mi.indicador_nome, mi.periodo_inicio,
               mi.periodo_label, mi.geografia, mi.unidade, mi.valor, mi.dimensoes
        from public.mercado_indicadores mi
        left join public.market_indicator_metadata mim
          on mim.source_key = mi.source_key
         and mim.indicator_key = mi.indicador_key
         and mim.active = true
        where mi.source_key = %s
          and mi.indicador_key = %s
          and (%s::text is null or mi.dimensoes->>'classification_code' = %s)
          and mi.valor is not null
          and (%s::date is null or mi.periodo_inicio <= %s::date)
          and (
            mim.source_key is null
            or (
              (mim.allow_zero or mi.valor <> 0)
              and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
              and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
            )
          )
        order by mi.periodo_inicio desc nulls last, mi.coletado_em desc
        limit 1
        """,
        (source_key, indicator_key, classification_code, classification_code, date_to, date_to),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "source_key": row[0],
        "indicator_key": row[1],
        "name": row[2],
        "period": row[3],
        "period_iso": row[3].isoformat() if row[3] else None,
        "period_label": row[4],
        "geography": row[5],
        "unit": row[6],
        "value": row[7],
        "value_text": market_decimal(row[7]),
        "dimensions": row[8] or {},
    }


def market_indicator_series_dimension_between(
    cur: Any,
    *,
    source_key: str,
    indicator_key: str,
    date_from: date | None = None,
    date_to: date | None = None,
    classification_code: str | None = None,
    limit: int = 36,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        select mi.periodo_inicio, mi.periodo_label, avg(mi.valor) as valor
        from public.mercado_indicadores mi
        left join public.market_indicator_metadata mim
          on mim.source_key = mi.source_key
         and mim.indicator_key = mi.indicador_key
         and mim.active = true
        where mi.source_key = %s
          and mi.indicador_key = %s
          and (%s::text is null or mi.dimensoes->>'classification_code' = %s)
          and mi.valor is not null
          and (%s::date is null or mi.periodo_inicio >= %s::date)
          and (%s::date is null or mi.periodo_inicio <= %s::date)
          and (
            mim.source_key is null
            or (
              (mim.allow_zero or mi.valor <> 0)
              and (mim.min_sanity_value is null or mi.valor >= mim.min_sanity_value)
              and (mim.max_sanity_value is null or mi.valor <= mim.max_sanity_value)
            )
          )
        group by mi.periodo_inicio, mi.periodo_label
        order by mi.periodo_inicio desc nulls last
        limit %s
        """,
        (source_key, indicator_key, classification_code, classification_code, date_from, date_from, date_to, date_to, limit),
    )
    rows = cur.fetchall()
    return [
        {
            "period": row[0],
            "period_iso": row[0].isoformat() if row[0] else None,
            "period_label": row[1],
            "value": row[2],
        }
        for row in reversed(rows)
    ]


def market_driver_snapshot(cur: Any, driver_key: str, cutoff: date | None) -> dict[str, Any]:
    config = INDUSTRY_DRIVER_DEFINITIONS[driver_key]
    latest = market_latest_indicator_dimension_before(
        cur,
        source_key=config["source_key"],
        indicator_key=config["indicator_key"],
        classification_code=config.get("classification_code"),
        date_to=cutoff,
    )
    if not latest:
        return {
            "key": driver_key,
            "label": config["label"],
            "source": config["source"],
            "kind": config["kind"],
            "value": None,
            "raw_value": None,
            "yoy": None,
            "signal": None,
            "period": None,
            "period_label": None,
            "unit": None,
            "status": "N/D",
        }
    value = latest["value"]
    normalized_value = market_normalize_cni_value(value) if config["kind"] == "cni50" else value
    yoy = None
    if config["kind"] == "yoy" and latest.get("period"):
        previous = market_latest_indicator_dimension_before(
            cur,
            source_key=config["source_key"],
            indicator_key=config["indicator_key"],
            classification_code=config.get("classification_code"),
            date_to=market_one_year_before(latest["period"]),
        )
        yoy = market_pct_change(normalized_value, previous["value"] if previous else None)
    signal = market_driver_signal(config["kind"], normalized_value, yoy)
    return {
        "key": driver_key,
        "label": config["label"],
        "source": config["source"],
        "kind": config["kind"],
        "value": market_decimal(normalized_value),
        "raw_value": market_decimal(value),
        "yoy": market_decimal(yoy),
        "signal": signal,
        "period": latest.get("period_iso"),
        "period_label": latest.get("period_label"),
        "unit": latest.get("unit"),
        "status": "OK",
    }


def market_family_index(driver_map: dict[str, dict[str, Any]], weights: dict[str, Decimal]) -> tuple[Decimal | None, list[dict[str, Any]]]:
    weighted_sum = Decimal("0")
    available_weight = Decimal("0")
    rows: list[dict[str, Any]] = []
    for driver_key, weight in weights.items():
        driver = driver_map.get(driver_key)
        signal = driver.get("signal") if driver else None
        if signal is not None:
            weighted_sum += Decimal(signal) * weight
            available_weight += weight
        rows.append(
            {
                "key": driver_key,
                "label": INDUSTRY_DRIVER_DEFINITIONS[driver_key]["label"],
                "weight": market_decimal(weight * Decimal("100")),
                "signal": signal,
                "value": driver.get("value") if driver else None,
                "yoy": driver.get("yoy") if driver else None,
                "period": driver.get("period") if driver else None,
                "period_label": driver.get("period_label") if driver else None,
                "source": driver.get("source") if driver else INDUSTRY_DRIVER_DEFINITIONS[driver_key]["source"],
            }
        )
    if available_weight == 0:
        return None, rows
    return (weighted_sum / available_weight) * Decimal("100"), rows


def market_industry_decision(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    driver_keys = sorted({key for weights in INDUSTRY_FAMILY_WEIGHTS.values() for key in weights})
    driver_map = {key: market_driver_snapshot(cur, key, date_to) for key in driver_keys}

    history_start = date_from or ((date_to or date.today()) - timedelta(days=760))
    monthly_indexes: dict[str, dict[str, Any]] = {}
    all_periods: set[date] = set()
    driver_series: dict[str, dict[date, dict[str, Any]]] = {}
    for driver_key in driver_keys:
        config = INDUSTRY_DRIVER_DEFINITIONS[driver_key]
        series = market_indicator_series_dimension_between(
            cur,
            source_key=config["source_key"],
            indicator_key=config["indicator_key"],
            classification_code=config.get("classification_code"),
            date_from=history_start,
            date_to=date_to,
            limit=36,
        )
        by_period: dict[date, dict[str, Any]] = {}
        for item in series:
            period = item["period"]
            if not period:
                continue
            value = item["value"]
            normalized = market_normalize_cni_value(value) if config["kind"] == "cni50" else value
            previous = next((p for p in series if p["period"] == market_one_year_before(period)), None)
            previous_value = previous["value"] if previous else None
            previous_normalized = market_normalize_cni_value(previous_value) if config["kind"] == "cni50" else previous_value
            yoy = market_pct_change(normalized, previous_normalized) if config["kind"] == "yoy" else None
            signal = market_driver_signal(config["kind"], normalized, yoy)
            by_period[period] = {
                "value": normalized,
                "yoy": yoy,
                "signal": signal,
                "period_label": item["period_label"],
            }
            all_periods.add(period)
        driver_series[driver_key] = by_period

    for period in sorted(all_periods):
        point = {"period": period.isoformat(), "period_label": None}
        period_driver_map: dict[str, dict[str, Any]] = {}
        for driver_key, by_period in driver_series.items():
            if period in by_period:
                period_driver_map[driver_key] = by_period[period]
                point["period_label"] = by_period[period]["period_label"]
        for family, weights in INDUSTRY_FAMILY_WEIGHTS.items():
            index, _rows = market_family_index(period_driver_map, weights)
            point[family] = market_decimal(index)
        monthly_indexes[period.isoformat()] = point

    latest_period = max(all_periods).isoformat() if all_periods else None
    three_month_reference: dict[str, Any] | None = None
    if all_periods:
        latest_date = max(all_periods)
        cutoff = latest_date - timedelta(days=92)
        previous_periods = [period for period in all_periods if period <= cutoff]
        if previous_periods:
            three_month_reference = monthly_indexes[max(previous_periods).isoformat()]

    families = []
    heatmap = []
    for family, weights in INDUSTRY_FAMILY_WEIGHTS.items():
        index, drivers = market_family_index(driver_map, weights)
        previous_index = None
        if three_month_reference:
            previous_value = three_month_reference.get(family)
            previous_index = Decimal(str(previous_value)) if previous_value not in (None, "") else None
        trend_3m = (index - previous_index) if index is not None and previous_index is not None else None
        positive = len([row for row in drivers if row["signal"] == 1])
        negative = len([row for row in drivers if row["signal"] == -1])
        available = len([row for row in drivers if row["signal"] is not None])
        coverage = f"{available}/{len(drivers)}"
        families.append(
            {
                "family": family,
                "classification": market_demand_classification(index),
                "index": market_decimal(index),
                "trend_3m": market_decimal(trend_3m),
                "trend_direction": (
                    "melhorando" if trend_3m is not None and trend_3m > 0
                    else "piorando" if trend_3m is not None and trend_3m < 0
                    else "estavel"
                ),
                "positive_drivers": positive,
                "negative_drivers": negative,
                "coverage": coverage,
                "drivers": drivers,
            }
        )
        for row in drivers:
            heatmap.append(
                {
                    "family": family,
                    "driver": row["label"],
                    "driver_key": row["key"],
                    "signal": row["signal"],
                    "weight": row["weight"],
                    "value": row["value"],
                    "yoy": row["yoy"],
                    "period": row["period"],
                    "period_label": row["period_label"],
                    "source": row["source"],
                }
            )

    def card_for(driver_key: str, title: str) -> dict[str, Any]:
        driver = driver_map.get(driver_key, {})
        value = driver.get("value")
        kind = driver.get("kind")
        if kind == "yoy":
            display_value = driver.get("yoy")
            unit = "%"
            detail = "YoY"
        elif value is not None:
            normalized = Decimal(str(value))
            display_value = market_decimal(normalized)
            unit = "indice"
            detail = market_decimal(normalized - Decimal("50"))
        else:
            display_value = None
            unit = "indice"
            detail = None
        return {
            "id": driver_key,
            "title": title,
            "value": display_value,
            "unit": unit,
            "detail": detail,
            "source": driver.get("source"),
            "period": driver.get("period"),
            "period_label": driver.get("period_label"),
        }

    production_chart = []
    for period in sorted(all_periods):
        row = {"period": period.isoformat(), "period_label": None}
        for driver_key, output_key in (
            ("produtos_metal", "produtos_metal"),
            ("maquinas", "maquinas"),
            ("metalurgia", "metalurgia"),
        ):
            point = driver_series.get(driver_key, {}).get(period)
            if point:
                row["period_label"] = point["period_label"]
                row[output_key] = market_decimal(point["value"])
                row[f"{output_key}_yoy"] = market_decimal(point["yoy"])
        if any(key in row for key in ("produtos_metal", "maquinas", "metalurgia")):
            production_chart.append(row)

    expectations_chart = []
    for period in sorted(all_periods):
        row = {"period": period.isoformat(), "period_label": None, "neutral": "50"}
        for driver_key, output_key in (
            ("cni_demanda", "demanda"),
            ("cni_compras", "compras"),
            ("cni_construcao_insumos", "insumos_construcao"),
        ):
            point = driver_series.get(driver_key, {}).get(period)
            if point:
                row["period_label"] = point["period_label"]
                row[output_key] = market_decimal(point["value"])
        if any(key in row for key in ("demanda", "compras", "insumos_construcao")):
            expectations_chart.append(row)

    readings = []
    weakest = min([item for item in families if item["index"] is not None], key=lambda item: Decimal(str(item["index"])), default=None)
    strongest = max([item for item in families if item["index"] is not None], key=lambda item: Decimal(str(item["index"])), default=None)
    if weakest:
        readings.append(
            {
                "key": "weakest_family",
                "severity": "attention" if weakest["negative_drivers"] > weakest["positive_drivers"] else "neutral",
                "text": f"{weakest['family']}: {weakest['negative_drivers']} drivers negativos; indice {weakest['index']} e tendencia 3M {weakest['trend_direction']}.",
            }
        )
    if strongest and strongest != weakest:
        readings.append(
            {
                "key": "strongest_family",
                "severity": "positive" if strongest["positive_drivers"] > strongest["negative_drivers"] else "neutral",
                "text": f"{strongest['family']}: melhor sinal relativo, indice {strongest['index']} com cobertura {strongest['coverage']}.",
            }
        )
    cni_demand = driver_map.get("cni_demanda", {})
    cni_purchases = driver_map.get("cni_compras", {})
    if cni_demand.get("value") is not None and cni_purchases.get("value") is not None:
        readings.append(
            {
                "key": "cni_expectations",
                "severity": "positive" if Decimal(str(cni_demand["value"])) > 50 and Decimal(str(cni_purchases["value"])) > 50 else "attention",
                "text": f"Expectativas CNI: demanda {cni_demand['value']} e compras {cni_purchases['value']} na escala oficial de 50 pontos.",
            }
        )

    return {
        "latest_period": latest_period,
        "cards": [
            card_for("produtos_metal", "Produtos de Metal"),
            card_for("maquinas", "Maquinas e Equipamentos"),
            card_for("cni_demanda", "Expectativa de Demanda"),
            card_for("cni_compras", "Compra de Materia-Prima"),
        ],
        "families": families,
        "demand_chart": list(monthly_indexes.values()),
        "heatmap": heatmap,
        "production_chart": production_chart,
        "expectations_chart": expectations_chart,
        "readings": readings,
        "methodology": {
            "index_scale": "-100 a +100",
            "yoy_signal": "> +2% = +1; -2% a +2% = 0; < -2% = -1",
            "cni_signal": "> 52 = +1; 48 a 52 = 0; < 48 = -1",
        },
    }


CONSTRUCTION_DRIVER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ibge_construcao": {
        "label": "IBGE Construcao",
        "source_key": "ibge_construcao_sidra",
        "indicator_key": "ibge_construcao_indice",
        "kind": "yoy",
        "source": "IBGE 8886",
    },
    "cni_atividade": {
        "label": "CNI Atividade",
        "source_key": "cni_sondagem_construcao",
        "indicator_key": "cni_construcao_9_expectativa_do_nivel_de_atividade_para_os_proximos_seis_meses",
        "kind": "cni50",
        "source": "CNI Construcao",
    },
    "cni_insumos": {
        "label": "CNI Compra Insumos",
        "source_key": "cni_sondagem_construcao",
        "indicator_key": "cni_construcao_10_expectativa_de_compras_de_insumos_e_materias_primas_para_os_proximos_seis_meses",
        "kind": "cni50",
        "source": "CNI Construcao",
    },
    "cni_novos": {
        "label": "CNI Novos Empreend.",
        "source_key": "cni_sondagem_construcao",
        "indicator_key": "cni_construcao_11_expectativa_de_novos_empreendimentos_e_servicos_para_os_proximos_seis_meses",
        "kind": "cni50",
        "source": "CNI Construcao",
    },
    "cni_emprego": {
        "label": "CNI Emprego",
        "source_key": "cni_sondagem_construcao",
        "indicator_key": "cni_construcao_12_expectativa_do_numero_de_empregados_para_os_proximos_seis_meses",
        "kind": "cni50",
        "source": "CNI Construcao",
    },
    "caged_construcao": {
        "label": "Caged Construcao",
        "source_key": "caged_microdados",
        "indicator_key": "caged_construcao_saldo",
        "kind": "balance",
        "source": "Caged",
    },
    "projetos": {
        "label": "Projetos",
        "source_key": "pncp_consulta",
        "indicator_key": "relevant_projects",
        "kind": "projects",
        "source": "PNCP / ObrasGov",
    },
}


CONSTRUCTION_FAMILY_WEIGHTS: dict[str, dict[str, Decimal]] = {
    "TELHAS": {
        "ibge_construcao": Decimal("0.20"),
        "cni_insumos": Decimal("0.25"),
        "cni_novos": Decimal("0.25"),
        "caged_construcao": Decimal("0.15"),
        "projetos": Decimal("0.15"),
    },
    "PERFIS": {
        "ibge_construcao": Decimal("0.20"),
        "cni_novos": Decimal("0.25"),
        "cni_insumos": Decimal("0.20"),
        "caged_construcao": Decimal("0.15"),
        "projetos": Decimal("0.20"),
    },
    "TUBOS / METALONS": {
        "ibge_construcao": Decimal("0.20"),
        "cni_atividade": Decimal("0.20"),
        "cni_insumos": Decimal("0.20"),
        "caged_construcao": Decimal("0.20"),
        "projetos": Decimal("0.20"),
    },
    "CHAPAS": {
        "ibge_construcao": Decimal("0.25"),
        "cni_insumos": Decimal("0.25"),
        "cni_novos": Decimal("0.20"),
        "projetos": Decimal("0.30"),
    },
}


PROJECT_RELEVANCE_TERMS: tuple[tuple[str, int], ...] = (
    ("estrutura metalica", 5),
    ("estrutura metálica", 5),
    ("cobertura metalica", 5),
    ("cobertura metálica", 5),
    ("telha metalica", 5),
    ("telha metálica", 5),
    ("perfil metalico", 5),
    ("perfil metálico", 5),
    ("tubo de aco", 5),
    ("tubo de aço", 5),
    ("metalon", 5),
    ("chapa de aco", 5),
    ("chapa de aço", 5),
    ("galpao", 4),
    ("galpão", 4),
    ("serralheria", 3),
    ("gradil", 2),
    ("alambrado", 2),
    ("aco", 1),
    ("aço", 1),
    ("construcao", 1),
    ("construção", 1),
    ("reforma", 1),
)


def market_ascii(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(char)
    )


def construction_project_matches(text: str) -> tuple[int, list[str], list[str]]:
    normalized = market_ascii(text)
    score = 0
    matches: list[str] = []
    products: set[str] = set()
    for term, weight in PROJECT_RELEVANCE_TERMS:
        normalized_term = market_ascii(term)
        if normalized_term in normalized:
            score += weight
            matches.append(term)
            if normalized_term in {"cobertura metalica", "galpao"}:
                products.update(["TELHAS", "PERFIS", "TUBOS / METALONS"])
            elif normalized_term in {"estrutura metalica"}:
                products.update(["PERFIS", "TUBOS / METALONS", "CHAPAS"])
            elif normalized_term in {"telha metalica"}:
                products.add("TELHAS")
            elif normalized_term in {"perfil metalico"}:
                products.add("PERFIS")
            elif normalized_term in {"tubo de aco", "metalon", "gradil", "alambrado"}:
                products.add("TUBOS / METALONS")
            elif normalized_term in {"chapa de aco"}:
                products.add("CHAPAS")
            elif normalized_term == "serralheria":
                products.update(["TUBOS / METALONS", "PERFIS"])
    return score, sorted(set(matches)), sorted(products)


def construction_signal_label(score: int | None, valid_count: int) -> str:
    if score is None or valid_count < 3:
        return "INSUFFICIENT_DATA"
    if score >= 2:
        return "ACELERANDO"
    if score <= -2:
        return "DESACELERANDO"
    return "ESTAVEL / MISTO"


def construction_driver_snapshot(
    cur: Any,
    driver_key: str,
    cutoff: date | None,
    *,
    relevant_projects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = CONSTRUCTION_DRIVER_DEFINITIONS[driver_key]
    if config["kind"] == "projects":
        projects = relevant_projects or []
        high_count = len([item for item in projects if item["relevance_score"] >= 5])
        signal = 1 if high_count >= 3 else 0 if projects else None
        return {
            "key": driver_key,
            "label": config["label"],
            "source": config["source"],
            "kind": config["kind"],
            "value": str(len(projects)) if projects else None,
            "raw_value": str(len(projects)) if projects else None,
            "yoy": None,
            "signal": signal,
            "period": cutoff.isoformat() if cutoff else None,
            "period_label": cutoff.strftime("%m/%y") if cutoff else None,
            "unit": "projetos",
            "status": "OK" if projects else "N/D",
        }
    latest = market_latest_indicator_before(cur, config["source_key"], config["indicator_key"], cutoff)
    if not latest:
        return {
            "key": driver_key,
            "label": config["label"],
            "source": config["source"],
            "kind": config["kind"],
            "value": None,
            "raw_value": None,
            "yoy": None,
            "signal": None,
            "period": None,
            "period_label": None,
            "unit": None,
            "status": "N/D",
        }
    value = latest["value"]
    normalized_value = market_normalize_cni_value(value) if config["kind"] == "cni50" else value
    yoy = None
    if config["kind"] == "yoy":
        previous = market_latest_indicator_before(cur, config["source_key"], config["indicator_key"], market_one_year_before(latest["period"]))
        yoy = market_pct_change(normalized_value, previous["value"] if previous else None)
    signal = market_driver_signal(config["kind"], normalized_value, yoy)
    if config["kind"] == "balance":
        signal = 1 if normalized_value and normalized_value > 0 else -1 if normalized_value and normalized_value < 0 else 0
    return {
        "key": driver_key,
        "label": config["label"],
        "source": config["source"],
        "kind": config["kind"],
        "value": market_decimal(normalized_value),
        "raw_value": market_decimal(value),
        "yoy": market_decimal(yoy),
        "signal": signal,
        "period": latest.get("period_iso"),
        "period_label": latest.get("period_label"),
        "unit": latest.get("unit"),
        "status": "OK",
    }


def construction_relevant_projects(cur: Any, date_from: date | None, date_to: date | None, limit: int = 20) -> list[dict[str, Any]]:
    try:
        cur.execute(
            """
            select data_publicacao, coalesce(uf, ''), coalesce(municipio, ''), coalesce(orgao, ''),
                   coalesce(objeto, ''), valor_estimado, coalesce(relevance_score, 0), pncp_id
            from public.fact_pncp_opportunities
            where (%s::date is null or data_publicacao >= %s::date)
              and (%s::date is null or data_publicacao <= %s::date)
              and upper(coalesce(uf, '')) in ('MG', 'SP')
            order by relevance_score desc, valor_estimado desc nulls last, data_publicacao desc nulls last
            limit 200
            """,
            (date_from, date_from, date_to, date_to),
        )
    except Exception:
        return []
    projects = []
    for row in cur.fetchall():
        calculated_score, matches, products = construction_project_matches(row[4] or "")
        score = max(int(row[6] or 0), calculated_score)
        if score < 3:
            continue
        projects.append(
            {
                "date": row[0].isoformat() if row[0] else None,
                "uf": row[1],
                "municipality": row[2],
                "pole": row[2] or row[1] or "ABR",
                "agency": row[3],
                "object": row[4],
                "value": market_decimal(row[5]),
                "relevance_score": score,
                "matches": matches,
                "products": products,
                "status": "monitorar",
                "link": "",
                "id": row[7],
            }
        )
    projects.sort(key=lambda item: (item["relevance_score"], Decimal(str(item["value"] or "0"))), reverse=True)
    return projects[:limit]


def construction_family_index(driver_map: dict[str, dict[str, Any]], weights: dict[str, Decimal]) -> tuple[Decimal | None, list[dict[str, Any]]]:
    weighted_sum = Decimal("0")
    available_weight = Decimal("0")
    rows: list[dict[str, Any]] = []
    for driver_key, weight in weights.items():
        driver = driver_map.get(driver_key)
        signal = driver.get("signal") if driver else None
        if signal is not None:
            weighted_sum += Decimal(signal) * weight
            available_weight += weight
        rows.append(
            {
                "key": driver_key,
                "label": CONSTRUCTION_DRIVER_DEFINITIONS[driver_key]["label"],
                "weight": market_decimal(weight * Decimal("100")),
                "signal": signal,
                "value": driver.get("value") if driver else None,
                "yoy": driver.get("yoy") if driver else None,
                "period": driver.get("period") if driver else None,
                "period_label": driver.get("period_label") if driver else None,
                "source": driver.get("source") if driver else CONSTRUCTION_DRIVER_DEFINITIONS[driver_key]["source"],
            }
        )
    if available_weight == 0:
        return None, rows
    return (weighted_sum / available_weight) * Decimal("100"), rows


def market_construction_decision(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    relevant_projects = construction_relevant_projects(cur, date_from, date_to)
    driver_keys = sorted({key for weights in CONSTRUCTION_FAMILY_WEIGHTS.values() for key in weights} | {"cni_emprego"})
    driver_map = {
        key: construction_driver_snapshot(cur, key, date_to, relevant_projects=relevant_projects)
        for key in driver_keys
    }

    general_keys = ["ibge_construcao", "cni_atividade", "cni_insumos", "cni_novos", "caged_construcao"]
    general_components = [driver_map[key] for key in general_keys if key in driver_map]
    valid_signals = [item["signal"] for item in general_components if item.get("signal") is not None]
    general_score = sum(valid_signals) if valid_signals else None
    general_signal = construction_signal_label(general_score, len(valid_signals))

    history_start = date_from or ((date_to or date.today()) - timedelta(days=760))
    series_map: dict[str, dict[date, dict[str, Any]]] = {}
    all_periods: set[date] = set()
    for key, config in CONSTRUCTION_DRIVER_DEFINITIONS.items():
        if config["kind"] in {"projects", "balance"}:
            continue
        series = market_indicator_series_dimension_between(
            cur,
            source_key=config["source_key"],
            indicator_key=config["indicator_key"],
            date_from=history_start,
            date_to=date_to,
            limit=36,
        )
        by_period: dict[date, dict[str, Any]] = {}
        values: list[Decimal] = []
        for item in series:
            period = item["period"]
            if not period:
                continue
            value = market_normalize_cni_value(item["value"]) if config["kind"] == "cni50" else item["value"]
            med = median(values[-6:]) if len(values) >= 3 else None
            suspect = bool(med and value is not None and value < Decimal(str(med)) * Decimal("0.20"))
            if value is not None and not suspect:
                values.append(value)
            previous = next((point for point in series if point["period"] == market_one_year_before(period)), None)
            previous_value = previous["value"] if previous else None
            previous_normalized = market_normalize_cni_value(previous_value) if config["kind"] == "cni50" else previous_value
            yoy = market_pct_change(value, previous_normalized) if config["kind"] == "yoy" and not suspect else None
            by_period[period] = {
                "value": None if suspect else value,
                "yoy": yoy,
                "signal": None if suspect else market_driver_signal(config["kind"], value, yoy),
                "period_label": item["period_label"],
                "suspect": suspect,
            }
            all_periods.add(period)
        series_map[key] = by_period

    monthly_indexes: dict[str, dict[str, Any]] = {}
    for period in sorted(all_periods):
        point: dict[str, Any] = {"period": period.isoformat(), "period_label": None}
        period_driver_map: dict[str, dict[str, Any]] = {}
        for key, by_period in series_map.items():
            if period in by_period:
                period_driver_map[key] = by_period[period]
                point["period_label"] = by_period[period]["period_label"]
        for key in ("caged_construcao", "projetos"):
            if driver_map.get(key):
                period_driver_map[key] = driver_map[key]
        for family, weights in CONSTRUCTION_FAMILY_WEIGHTS.items():
            index, _rows = construction_family_index(period_driver_map, weights)
            point[family] = market_decimal(index)
        monthly_indexes[period.isoformat()] = point

    three_month_reference = None
    if all_periods:
        latest_date = max(all_periods)
        previous_periods = [period for period in all_periods if period <= latest_date - timedelta(days=92)]
        if previous_periods:
            three_month_reference = monthly_indexes[max(previous_periods).isoformat()]

    families = []
    heatmap = []
    for family, weights in CONSTRUCTION_FAMILY_WEIGHTS.items():
        index, drivers = construction_family_index(driver_map, weights)
        previous_index = None
        if three_month_reference:
            previous_value = three_month_reference.get(family)
            previous_index = Decimal(str(previous_value)) if previous_value not in (None, "") else None
        trend_3m = (index - previous_index) if index is not None and previous_index is not None else None
        positives = len([row for row in drivers if row["signal"] == 1])
        neutrals = len([row for row in drivers if row["signal"] == 0])
        negatives = len([row for row in drivers if row["signal"] == -1])
        available = positives + neutrals + negatives
        families.append(
            {
                "family": family,
                "classification": market_demand_classification(index),
                "index": market_decimal(index),
                "trend_3m": market_decimal(trend_3m),
                "trend_direction": (
                    "melhorando" if trend_3m is not None and trend_3m > Decimal("10")
                    else "piorando" if trend_3m is not None and trend_3m < Decimal("-10")
                    else "estavel"
                ),
                "positive_drivers": positives,
                "neutral_drivers": neutrals,
                "negative_drivers": negatives,
                "coverage": f"{available}/{len(drivers)}",
                "drivers": drivers,
            }
        )
        for row in drivers:
            heatmap.append({"family": family, "driver": row["label"], "driver_key": row["key"], **row})

    def card(driver_key: str, title: str) -> dict[str, Any]:
        driver = driver_map.get(driver_key, {})
        value = driver.get("value")
        return {
            "id": driver_key,
            "title": title,
            "value": driver.get("yoy") if driver.get("kind") == "yoy" else value,
            "unit": "%" if driver.get("kind") == "yoy" else driver.get("unit") or "indice",
            "detail": (
                "YoY"
                if driver.get("kind") == "yoy"
                else market_decimal(Decimal(str(value)) - Decimal("50")) if value not in (None, "") and driver.get("unit") == "indice"
                else "12M" if driver.get("kind") == "balance"
                else "RelevanceScore >= 3"
            ),
            "source": driver.get("source"),
            "period": driver.get("period"),
            "period_label": driver.get("period_label"),
            "raw_value": driver.get("raw_value"),
            "scale_factor": "0.1" if driver.get("kind") == "cni50" and driver.get("raw_value") and driver.get("value") and Decimal(str(driver["raw_value"])) > Decimal("100") else "1",
            "neutral_value": "50" if driver.get("kind") == "cni50" else None,
        }

    activity_chart = []
    ibge_points = series_map.get("ibge_construcao", {})
    ibge_values: list[Decimal] = []
    for period in sorted(ibge_points):
        point = ibge_points[period]
        value = point.get("value")
        if value is not None:
            ibge_values.append(value)
        ma3 = sum(ibge_values[-3:]) / Decimal(len(ibge_values[-3:])) if ibge_values else None
        activity_chart.append(
            {
                "period": period.isoformat(),
                "period_label": point.get("period_label"),
                "index": market_decimal(value),
                "yoy": market_decimal(point.get("yoy")),
                "ma3": market_decimal(ma3),
                "status": "SUSPECT_VALUE" if point.get("suspect") else "OK",
            }
        )

    expectations_chart = []
    for period in sorted(all_periods):
        row = {"period": period.isoformat(), "period_label": None, "neutral": "50"}
        for key, output in (("cni_atividade", "atividade"), ("cni_insumos", "insumos"), ("cni_novos", "novos"), ("cni_emprego", "emprego")):
            point = series_map.get(key, {}).get(period)
            if point:
                row["period_label"] = point["period_label"]
                row[output] = market_decimal(point.get("value"))
        if any(name in row for name in ("atividade", "insumos", "novos", "emprego")):
            expectations_chart.append(row)

    readings = []
    ibge = driver_map.get("ibge_construcao", {})
    insumos = driver_map.get("cni_insumos", {})
    novos = driver_map.get("cni_novos", {})
    if ibge.get("yoy") is not None and Decimal(str(ibge["yoy"])) > Decimal("2") and insumos.get("value") and Decimal(str(insumos["value"])) > Decimal("52"):
        readings.append({"key": "construction_strength", "severity": "positive", "text": "Atividade da construcao e intencao de compra de insumos apontam fortalecimento da demanda."})
    if novos.get("value") and Decimal(str(novos["value"])) < Decimal("48"):
        readings.append({"key": "new_projects_low", "severity": "attention", "text": "Expectativa de novos empreendimentos esta abaixo da neutralidade."})
    best_family = max([item for item in families if item["index"] is not None], key=lambda item: Decimal(str(item["index"])), default=None)
    if best_family and Decimal(str(best_family["index"])) >= Decimal("30"):
        readings.append({"key": "family_positive", "severity": "positive", "text": f"{best_family['family']}: drivers apresentam predominancia positiva."})
    if relevant_projects:
        readings.append({"key": "relevant_projects", "severity": "positive", "text": f"Existem {len(relevant_projects)} projetos de aderencia ABR no recorte monitorado."})
    if not readings:
        readings.append({"key": "construction_mixed", "severity": "neutral", "text": "Sinais da construcao estao mistos; CNI recente pesa contra expansao no curto prazo."})

    return {
        "cards": [
            card("ibge_construcao", "Atividade da Construcao"),
            card("cni_atividade", "Expectativa de Atividade"),
            card("cni_insumos", "Compra Esperada de Insumos"),
            card("cni_novos", "Novos Empreendimentos"),
            card("caged_construcao", "Emprego Construcao"),
            {
                "id": "relevant_projects",
                "title": "Projetos ABR Relevantes",
                "value": str(len(relevant_projects)),
                "unit": "projetos",
                "detail": "PNCP MG/SP | RelevanceScore >= 3",
                "source": "PNCP",
                "period": date_to.isoformat() if date_to else None,
                "period_label": None,
                "raw_value": str(len(relevant_projects)),
                "scale_factor": "1",
                "neutral_value": None,
            },
        ],
        "signal": {
            "classification": general_signal,
            "score": general_score,
            "valid_drivers": len(valid_signals),
            "positive": len([value for value in valid_signals if value == 1]),
            "neutral": len([value for value in valid_signals if value == 0]),
            "negative": len([value for value in valid_signals if value == -1]),
            "components": general_components,
        },
        "families": families,
        "demand_chart": list(monthly_indexes.values()),
        "heatmap": heatmap,
        "activity_chart": activity_chart,
        "expectations_chart": expectations_chart,
        "projects": relevant_projects,
        "readings": readings[:4],
        "quality": {
            "cni_scale": "Valores CNI no banco auditados na escala oficial; normalizacao automatica apenas se raw_value > 100.",
            "null_rule": "Mes sem dado permanece null; valores suspeitos por queda artificial sao marcados como SUSPECT_VALUE.",
            "suspect_values": [
                {"period": item["period"], "value": item.get("index"), "status": item["status"]}
                for item in activity_chart
                if item["status"] == "SUSPECT_VALUE"
            ],
        },
    }


def market_steel_volume_series(
    cur: Any,
    indicator_key: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 48,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        select
          mi.periodo_inicio,
          mi.periodo_label,
          avg(mi.valor) as raw_value,
          avg(mi.valor * coalesce(mim.scale_factor, 1)) as normalized_value,
          max(coalesce(mim.normalized_unit, mi.unidade)) as normalized_unit,
          max(mi.unidade) as raw_unit,
          max(coalesce(mim.scale_factor, 1)) as scale_factor
        from public.mercado_indicadores mi
        left join public.market_indicator_metadata mim
          on mim.source_key = mi.source_key
         and mim.indicator_key = mi.indicador_key
         and mim.active = true
        where mi.source_key = 'aco_brasil_estatistica_mensal'
          and mi.indicador_key = %s
          and mi.valor is not null
          and (%s::date is null or mi.periodo_inicio >= %s::date)
          and (%s::date is null or mi.periodo_inicio <= %s::date)
          and (
            mim.source_key is null
            or (
              (mim.allow_zero or mi.valor <> 0)
              and (mim.min_sanity_value is null or (mi.valor * coalesce(mim.scale_factor, 1)) >= mim.min_sanity_value)
              and (mim.max_sanity_value is null or (mi.valor * coalesce(mim.scale_factor, 1)) <= mim.max_sanity_value)
            )
          )
        group by mi.periodo_inicio, mi.periodo_label
        order by mi.periodo_inicio desc nulls last
        limit %s
        """,
        (indicator_key, date_from, date_from, date_to, date_to, limit),
    )
    rows = cur.fetchall()
    series = [
        {
            "period": row[0],
            "period_iso": row[0].isoformat() if row[0] else None,
            "period_label": row[1],
            "raw_value": row[2],
            "value": row[3],
            "unit": row[4],
            "raw_unit": row[5],
            "scale_factor": row[6],
            "suspect": False,
            "quality": "OK",
        }
        for row in reversed(rows)
    ]
    previous_values: list[Decimal] = []
    for item in series:
        value = item["value"]
        if value is not None and len(previous_values) >= 6:
            window = sorted(previous_values[-6:])
            median_value = (window[2] + window[3]) / Decimal("2")
            if median_value and value < median_value * Decimal("0.2"):
                item["suspect"] = True
                item["quality"] = "SUSPECT_VALUE"
                item["value"] = None
        if value is not None:
            previous_values.append(value)
    return series


def market_steel_latest_from_series(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(series):
        if item.get("value") is not None and not item.get("suspect"):
            return item
    return None


def market_steel_yoy_from_latest(
    cur: Any,
    indicator_key: str,
    latest: dict[str, Any] | None,
) -> Decimal | None:
    if not latest or not latest.get("period") or latest.get("value") is None:
        return None
    previous_cutoff = market_one_year_before(latest["period"])
    previous_series = market_steel_volume_series(cur, indicator_key, date_to=previous_cutoff, limit=18)
    previous = market_steel_latest_from_series(previous_series)
    return market_pct_change(latest["value"], previous["value"] if previous else None)


def market_inda_latest(
    cur: Any,
    indicator_key: str,
    *,
    date_to: date | None = None,
) -> dict[str, Any] | None:
    return market_latest_indicator_before(cur, "inda_estatisticas", indicator_key, date_to)


def market_steel_signal_from_pct(value: Decimal | None, positive_threshold: Decimal, negative_threshold: Decimal | None = None) -> tuple[int, str, str]:
    if value is None:
        return 0, "sem comparativo", "Sem comparativo"
    negative = negative_threshold if negative_threshold is not None else -positive_threshold
    if value > positive_threshold:
        return 1, "↑", "alta"
    if value < negative:
        return -1, "↓", "queda"
    return 0, "→", "estavel"


def market_steel_balance_classification(demand_signal: int, supply_pressure: int) -> str:
    if demand_signal > 0 and supply_pressure <= 0:
        return "MERCADO MAIS APERTADO"
    if demand_signal > 0 and supply_pressure > 0:
        return "MERCADO EQUILIBRADO / DISPUTADO"
    if demand_signal < 0 and supply_pressure > 0:
        return "MERCADO MAIS FROUXO"
    if demand_signal < 0 and supply_pressure <= 0:
        return "BAIXA ATIVIDADE / OFERTA AJUSTADA"
    if supply_pressure > 0:
        return "OFERTA MAIS PRESENTE"
    if supply_pressure < 0:
        return "OFERTA MAIS AJUSTADA"
    return "MERCADO ESTAVEL"


def market_steel_decision(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    volume_indicators = {
        "internal_sales": ("aco_brasil_vendas_internas_total", "Vendas internas"),
        "consumption": ("aco_brasil_consumo_aparente_total", "Consumo aparente"),
        "flat_production": ("aco_brasil_producao_planos", "Producao de laminados planos"),
        "rolled_production": ("aco_brasil_producao_laminados", "Producao de laminados"),
        "imports": ("aco_brasil_importacoes_total_toneladas", "Importacoes"),
    }
    series = {
        key: market_steel_volume_series(cur, indicator_key, date_from=date_from, date_to=date_to, limit=48)
        for key, (indicator_key, _label) in volume_indicators.items()
    }
    latest = {key: market_steel_latest_from_series(value) for key, value in series.items()}
    production_key = "flat_production" if latest.get("flat_production") else "rolled_production"
    production_label = volume_indicators[production_key][1]
    yoy = {
        key: market_steel_yoy_from_latest(cur, volume_indicators[key][0], value)
        for key, value in latest.items()
    }

    def card(item_id: str, title: str, key: str, tooltip: str) -> dict[str, Any] | None:
        item = latest.get(key)
        if not item:
            return None
        return {
            "id": item_id,
            "title": title,
            "value_tons": market_decimal(item["value"]),
            "unit": "t",
            "yoy": market_decimal(yoy.get(key)),
            "source": "Aco Brasil",
            "competence": item.get("period_label") or item.get("period_iso"),
            "tooltip": tooltip,
            "raw_unit": item.get("raw_unit"),
            "normalized_unit": item.get("unit"),
            "scale_factor": market_decimal(item.get("scale_factor")),
        }

    cards = [
        card(
            "internal_sales",
            "Vendas internas",
            "internal_sales",
            "Vendas internas informadas pelo Instituto Aco Brasil. YoY = valor da competencia atual / mesma competencia do ano anterior - 1. Unidade normalizada: toneladas.",
        ),
        card(
            "consumption",
            "Consumo aparente",
            "consumption",
            "Consumo aparente representa uma medida do volume disponivel ao mercado interno, conforme metodologia da fonte. YoY = valor atual / mesma competencia do ano anterior - 1.",
        ),
        card(
            "flat_production",
            "Laminados planos" if production_key == "flat_production" else "Laminados",
            production_key,
            "Producao de laminados planos do Instituto Aco Brasil. Quando a serie de planos nao estiver disponivel, usa laminados total e informa no titulo.",
        ),
        card(
            "imports",
            "Importacoes",
            "imports",
            "Volume importado informado pelo Instituto Aco Brasil. Nao usa valor em dolar como substituto de volume.",
        ),
    ]
    cards = [item for item in cards if item]

    inda_keys = {
        "purchases_mom": "inda_compras_variacao_mes_pct",
        "sales_mom": "inda_vendas_variacao_mes_pct",
        "stock_mom": "inda_estoque_variacao_mes_pct",
        "imports_mom": "inda_importacao_variacao_mes_pct",
    }
    inda = {key: market_inda_latest(cur, indicator, date_to=date_to) for key, indicator in inda_keys.items()}
    demand_signal, demand_direction, demand_label = market_steel_signal_from_pct(yoy.get("consumption"), Decimal("3"))
    production_signal, production_direction, production_label_signal = market_steel_signal_from_pct(yoy.get(production_key), Decimal("3"))
    import_signal, import_direction, import_label = market_steel_signal_from_pct(yoy.get("imports"), Decimal("10"))
    stock_value = inda["stock_mom"]["value"] if inda.get("stock_mom") else None
    inventory_signal, inventory_direction, inventory_label = market_steel_signal_from_pct(stock_value, Decimal("2"))
    supply_pressure = production_signal + import_signal + inventory_signal
    demand_supply_gap = None
    if yoy.get("consumption") is not None and yoy.get(production_key) is not None:
        demand_supply_gap = yoy["consumption"] - yoy[production_key]

    market_reading = [
        {
            "dimension": "DEMANDA INTERNA",
            "indicator": "Consumo aparente",
            "value": market_decimal(latest["consumption"]["value"] if latest.get("consumption") else None),
            "variation": market_decimal(yoy.get("consumption")),
            "variation_label": "YoY",
            "direction": demand_direction,
            "signal": demand_label,
            "source": f"Aco Brasil | {latest['consumption']['period_label']}" if latest.get("consumption") else "Aco Brasil",
        },
        {
            "dimension": "OFERTA NACIONAL",
            "indicator": production_label,
            "value": market_decimal(latest[production_key]["value"] if latest.get(production_key) else None),
            "variation": market_decimal(yoy.get(production_key)),
            "variation_label": "YoY",
            "direction": production_direction,
            "signal": production_label_signal,
            "source": f"Aco Brasil | {latest[production_key]['period_label']}" if latest.get(production_key) else "Aco Brasil",
        },
        {
            "dimension": "IMPORTACOES",
            "indicator": "Importacoes",
            "value": market_decimal(latest["imports"]["value"] if latest.get("imports") else None),
            "variation": market_decimal(yoy.get("imports")),
            "variation_label": "YoY",
            "direction": import_direction,
            "signal": "alta forte" if yoy.get("imports") is not None and yoy["imports"] > Decimal("10") else import_label,
            "source": f"Aco Brasil | {latest['imports']['period_label']}" if latest.get("imports") else "Aco Brasil",
        },
        {
            "dimension": "ESTOQUE DO CANAL",
            "indicator": "Estoque INDA",
            "value": market_decimal(stock_value),
            "variation": market_decimal(stock_value),
            "variation_label": "MoM",
            "direction": inventory_direction,
            "signal": inventory_label,
            "source": f"INDA | {inda['stock_mom']['period_label']}" if inda.get("stock_mom") else "INDA",
        },
    ]

    periods = sorted({item["period_iso"] for values in series.values() for item in values if item.get("period_iso")})
    series_by_period = {
        key: {item.get("period_iso"): item for item in values if item.get("period_iso")}
        for key, values in series.items()
    }

    def point_yoy_from_series(source_key: str, period_iso: str | None, value: str | Decimal | None) -> Decimal | None:
        if not period_iso or value is None:
            return None
        point_date = date.fromisoformat(period_iso)
        previous_iso = market_one_year_before(point_date).isoformat()
        previous = series_by_period.get(source_key, {}).get(previous_iso)
        previous_value = previous.get("value") if previous else None
        current_value = Decimal(str(value))
        return market_pct_change(current_value, previous_value)

    demand_supply_chart = []
    yoy_chart = []
    import_pressure_chart = []
    for period in periods:
        row: dict[str, Any] = {"period": period, "period_label": period[:7] if period else None}
        yoy_row: dict[str, Any] = {"period": period, "period_label": period[:7] if period else None}
        for output_key, source_key in (
            ("internal_sales", "internal_sales"),
            ("consumption", "consumption"),
            ("production", production_key),
            ("imports", "imports"),
        ):
            point = next((item for item in series[source_key] if item.get("period_iso") == period), None)
            value = point.get("value") if point else None
            row[output_key] = market_decimal(value)
            if point and value is not None:
                point_yoy = point_yoy_from_series(source_key, period, value)
                yoy_row[output_key] = market_decimal(point_yoy)
        demand_supply_chart.append(row)
        yoy_chart.append(yoy_row)

    imports_base = next((numeric for numeric in (Decimal(str(row["imports"])) if row.get("imports") else None for row in demand_supply_chart) if numeric), None)
    consumption_base = next((numeric for numeric in (Decimal(str(row["consumption"])) if row.get("consumption") else None for row in demand_supply_chart) if numeric), None)
    for row in demand_supply_chart:
        imports_value = Decimal(str(row["imports"])) if row.get("imports") else None
        consumption_value = Decimal(str(row["consumption"])) if row.get("consumption") else None
        import_pressure_chart.append(
            {
                "period": row["period"],
                "period_label": row["period_label"],
                "imports_index": market_decimal((imports_value / imports_base) * 100 if imports_value is not None and imports_base else None),
                "consumption_index": market_decimal((consumption_value / consumption_base) * 100 if consumption_value is not None and consumption_base else None),
            }
        )

    distribution = []
    for key, label in (
        ("purchases_mom", "Compras"),
        ("sales_mom", "Vendas"),
        ("stock_mom", "Estoque"),
        ("imports_mom", "Importacoes"),
    ):
        item = inda.get(key)
        if item and item.get("value") is not None:
            distribution.append(
                {
                    "metric": label,
                    "value": market_decimal(item["value"]),
                    "period": item.get("period_iso"),
                    "period_label": item.get("period_label"),
                }
            )

    readings: list[dict[str, str]] = []
    if yoy.get("consumption") is not None and yoy.get(production_key) is not None and yoy["consumption"] > Decimal("3") and yoy[production_key] <= Decimal("1"):
        readings.append({"key": "consumption_above_production", "text": "Consumo esta crescendo acima da producao nacional.", "severity": "attention"})
    if yoy.get("imports") is not None and yoy["imports"] > Decimal("10"):
        readings.append({"key": "imports_intensity", "text": "Importacoes estao ganhando intensidade em relacao ao ano anterior.", "severity": "attention"})
    if inda.get("stock_mom") and inda.get("sales_mom") and inda["stock_mom"]["value"] > Decimal("2") and inda["sales_mom"]["value"] < 0:
        readings.append({"key": "channel_inventory", "text": "Estoques da distribuicao crescem enquanto vendas recuam.", "severity": "attention"})
    if yoy.get("consumption") is not None and yoy.get("imports") is not None and yoy["consumption"] > 0 and yoy["imports"] > yoy["consumption"] + Decimal("5"):
        readings.append({"key": "imports_above_market", "text": "Importacoes crescem acima do ritmo do mercado interno.", "severity": "attention"})
    if demand_supply_gap is not None:
        if demand_supply_gap > Decimal("3"):
            readings.append({"key": "demand_supply_gap", "text": "Demanda cresce mais rapido que a producao de laminados/planos.", "severity": "neutral"})
        elif demand_supply_gap < Decimal("-3"):
            readings.append({"key": "demand_supply_gap", "text": "Producao cresce mais rapido que o consumo aparente.", "severity": "neutral"})

    suspect_values = [
        {
            "indicator": volume_indicators[key][1],
            "period": item.get("period_label") or item.get("period_iso"),
            "raw_value": market_decimal(item.get("raw_value")),
            "normalized_value": market_decimal(item.get("value")),
            "rule": "SUSPECT_VALUE",
        }
        for key, values in series.items()
        for item in values
        if item.get("suspect")
    ]

    return {
        "kpis": cards,
        "market_reading": market_reading,
        "balance": {
            "classification": market_steel_balance_classification(demand_signal, supply_pressure),
            "demand_pressure": demand_signal,
            "supply_pressure": supply_pressure,
            "components": {
                "demand_signal": demand_signal,
                "production_signal": production_signal,
                "import_signal": import_signal,
                "inventory_signal": inventory_signal,
            },
            "demand_supply_gap": market_decimal(demand_supply_gap),
            "demand_supply_gap_label": (
                "demanda crescendo mais que producao"
                if demand_supply_gap is not None and demand_supply_gap > Decimal("3")
                else "producao crescendo mais que demanda"
                if demand_supply_gap is not None and demand_supply_gap < Decimal("-3")
                else "crescimento semelhante"
                if demand_supply_gap is not None
                else "sem comparativo"
            ),
        },
        "charts": {
            "demand_supply": demand_supply_chart,
            "yoy": yoy_chart,
            "import_pressure": import_pressure_chart,
            "distribution": distribution,
        },
        "decision_readings": readings[:4],
        "quality": {
            "suspect_values": suspect_values,
            "unit_rules": [
                {"indicator": item["title"], "raw_unit": item.get("raw_unit"), "normalized_unit": item.get("normalized_unit"), "scale_factor": item.get("scale_factor")}
                for item in cards
            ],
        },
    }


def market_comex_summary(cur: Any) -> dict[str, Any]:
    cur.execute("select max(periodo_inicio) from public.fact_steel_import_monthly")
    latest_period = cur.fetchone()[0]
    if not latest_period:
        return {}

    cur.execute(
        """
        select
          coalesce(sum(toneladas), 0),
          coalesce(sum(vl_fob_usd), 0),
          coalesce(sum(vl_frete_usd), 0),
          coalesce(sum(vl_seguro_usd), 0)
        from public.fact_steel_import_monthly
        where periodo_inicio >= (%s::date - interval '11 months')
        """,
        (latest_period,),
    )
    tons_12m, fob_12m, freight_12m, insurance_12m = cur.fetchone()
    fob_usd_t = (fob_12m / tons_12m) if tons_12m else None
    cif_proxy_usd_t = ((fob_12m + freight_12m + insurance_12m) / tons_12m) if tons_12m else None

    cur.execute(
        """
        select periodo_inicio, coalesce(sum(toneladas), 0), coalesce(sum(vl_fob_usd), 0),
               coalesce(sum(vl_frete_usd), 0), coalesce(sum(vl_seguro_usd), 0)
        from public.fact_steel_import_monthly
        group by periodo_inicio
        order by periodo_inicio desc
        limit 24
        """
    )
    monthly = []
    for period, tons, fob, freight, insurance in reversed(cur.fetchall()):
        monthly.append(
            {
                "period": period.isoformat(),
                "period_label": period.strftime("%m/%y"),
                "toneladas": market_decimal(tons),
                "fob_usd_t": market_decimal((fob / tons) if tons else None),
                "cif_proxy_usd_t": market_decimal(((fob + freight + insurance) / tons) if tons else None),
            }
        )

    cur.execute(
        """
        select coalesce(co_pais, 'NAO INFORMADO') as pais, coalesce(sum(toneladas), 0) as tons
        from public.fact_steel_import_monthly
        where periodo_inicio >= (%s::date - interval '11 months')
        group by coalesce(co_pais, 'NAO INFORMADO')
        order by tons desc
        limit 10
        """,
        (latest_period,),
    )
    countries = [{"country": row[0], "toneladas": market_decimal(row[1])} for row in cur.fetchall()]

    cur.execute(
        """
        select familia_abr, coalesce(sum(toneladas), 0), coalesce(sum(vl_fob_usd), 0)
        from public.fact_steel_import_monthly
        where periodo_inicio >= (%s::date - interval '11 months')
        group by familia_abr
        order by sum(toneladas) desc nulls last
        limit 10
        """,
        (latest_period,),
    )
    families = [
        {
            "family": row[0],
            "toneladas": market_decimal(row[1]),
            "fob_usd_t": market_decimal((row[2] / row[1]) if row[1] else None),
        }
        for row in cur.fetchall()
    ]

    cur.execute(
        """
        select ncm, familia_abr, coalesce(co_pais, 'NAO INFORMADO') as pais,
               coalesce(sum(toneladas), 0) as tons,
               coalesce(sum(vl_fob_usd), 0) as fob,
               coalesce(sum(vl_frete_usd), 0) as frete
        from public.fact_steel_import_monthly
        where periodo_inicio >= (%s::date - interval '11 months')
        group by ncm, familia_abr, coalesce(co_pais, 'NAO INFORMADO')
        order by tons desc
        limit 20
        """,
        (latest_period,),
    )
    detail = [
        {
            "ncm": row[0],
            "family": row[1],
            "country": row[2],
            "toneladas": market_decimal(row[3]),
            "fob_usd_t": market_decimal((row[4] / row[3]) if row[3] else None),
            "freight_usd_t": market_decimal((row[5] / row[3]) if row[3] else None),
        }
        for row in cur.fetchall()
    ]

    return {
        "latest_period": latest_period.isoformat(),
        "kpis": {
            "toneladas_12m": market_decimal(tons_12m),
            "fob_usd_t": market_decimal(fob_usd_t),
            "cif_proxy_usd_t": market_decimal(cif_proxy_usd_t),
            "countries": len(countries),
        },
        "monthly": monthly,
        "countries": countries,
        "families": families,
        "detail": detail,
    }


def market_ptax_summary(cur: Any) -> dict[str, Any]:
    series = market_indicator_series(cur, "bcb_dolar_ptax", "bcb_ptax_cotacaoVenda", limit=60)
    if not series:
        return {}
    latest = series[-1]
    first = series[0]
    latest_value = numericValue = Decimal(str(latest["value"])) if latest.get("value") else Decimal("0")
    first_value = Decimal(str(first["value"])) if first.get("value") else Decimal("0")
    change = ((latest_value / first_value) - Decimal("1")) * Decimal("100") if first_value else None
    return {
        "latest": latest,
        "change_period_pct": market_decimal(change),
        "series": series,
    }


def market_ptax_raw_series(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cur.execute(
        """
        with selected as (
          select distinct on (data_cotacao)
            data_cotacao,
            data_hora_cotacao,
            tipo_boletim,
            cotacao_venda,
            payload
          from public.raw_bcb_ptax
          where (%s::date is null or data_cotacao >= %s::date)
            and (%s::date is null or data_cotacao <= %s::date)
          order by
            data_cotacao,
            case
              when lower(coalesce(tipo_boletim, '')) like '%%fechamento%%' then 0
              when lower(coalesce(tipo_boletim, '')) like '%%ptax%%' then 1
              else 2
            end,
            data_hora_cotacao desc
        )
        select data_cotacao, data_hora_cotacao, tipo_boletim, cotacao_venda, payload
        from selected
        order by data_cotacao
        """,
        (date_from, date_from, date_to, date_to),
    )
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    values_for_ma: list[Decimal] = []
    for row in cur.fetchall():
        raw_value = row[3]
        normalized_value = raw_value
        error = None
        if normalized_value is None:
            error = "PTAX nula"
        elif normalized_value <= 0 or normalized_value >= 20:
            error = "PTAX fora da faixa de sanidade 0 < PTAX < 20"
        item = {
            "date": row[0].isoformat() if row[0] else None,
            "date_label": row[0].strftime("%d/%m") if row[0] else None,
            "reference_date": row[0].isoformat() if row[0] else None,
            "quoted_at": market_timestamp(row[1]),
            "bulletin_type": row[2],
            "raw_value": market_decimal(raw_value),
            "normalized_value": market_decimal(normalized_value),
            "value": market_decimal(normalized_value),
            "source": "BCB PTAX",
            "status": "INVALID" if error else "VALID",
            "validation_error": error,
        }
        if error:
            invalid.append(item)
            continue
        values_for_ma.append(normalized_value)
        window = values_for_ma[-20:]
        item["ma20"] = market_decimal(sum(window) / Decimal(len(window)) if window else None)
        valid.append(item)
    return valid, invalid


def market_closest_ptax_before(cur: Any, target: date) -> dict[str, Any] | None:
    series, _invalid = market_ptax_raw_series(cur, date_to=target)
    return series[-1] if series else None


def market_comex_readiness(cur: Any, date_from: date | None = None, date_to: date | None = None) -> dict[str, Any]:
    cur.execute("select count(*)::int from public.dim_ncm_abr where ativo = true")
    active_ncms = int(cur.fetchone()[0] or 0)
    if active_ncms == 0:
        return {
            "status": "NO_NCM_MAPPING",
            "active_ncms": 0,
            "records": 0,
            "message": "Pressao especifica por familia aguardando mapeamento NCM/Comex.",
        }
    cur.execute(
        """
        select count(*)::int, coalesce(sum(toneladas), 0), coalesce(sum(vl_fob_usd), 0)
        from public.fact_steel_import_monthly
        where (%s::date is null or periodo_inicio >= %s::date)
          and (%s::date is null or periodo_inicio <= %s::date)
        """,
        (date_from, date_from, date_to, date_to),
    )
    records, tons, fob = cur.fetchone()
    if not records:
        return {
            "status": "NO_COMEX_DATA",
            "active_ncms": active_ncms,
            "records": 0,
            "message": "NCMs existem, mas nao ha registros Comex validos no periodo.",
        }
    if not tons or tons <= 0 or not fob or fob <= 0:
        return {
            "status": "INSUFFICIENT_DATA",
            "active_ncms": active_ncms,
            "records": int(records or 0),
            "message": "Comex sem peso liquido ou valor FOB validos no periodo.",
        }
    return {
        "status": "READY",
        "active_ncms": active_ncms,
        "records": int(records or 0),
        "message": "Comex pronto para analise por familia.",
    }


def market_prices_decision(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    ptax_series, invalid_values = market_ptax_raw_series(cur, date_from=date_from, date_to=date_to)
    latest = ptax_series[-1] if ptax_series else None
    first = ptax_series[0] if ptax_series else None
    latest_value = Decimal(str(latest["value"])) if latest and latest.get("value") else None
    first_value = Decimal(str(first["value"])) if first and first.get("value") else None
    period_change = market_pct_change(latest_value, first_value)
    fx_30d = None
    if latest and latest.get("reference_date") and latest_value is not None:
        previous_30d = market_closest_ptax_before(cur, date.fromisoformat(latest["reference_date"]) - timedelta(days=30))
        previous_30d_value = Decimal(str(previous_30d["value"])) if previous_30d and previous_30d.get("value") else None
        fx_30d = market_pct_change(latest_value, previous_30d_value)
    average_value = None
    if ptax_series:
        valid_values = [Decimal(str(item["value"])) for item in ptax_series if item.get("value")]
        average_value = sum(valid_values) / Decimal(len(valid_values)) if valid_values else None
    comex_status = market_comex_readiness(cur, date_from=date_from, date_to=date_to)

    cards: list[dict[str, Any]] = []
    if latest:
        cards.append(
            {
                "id": "ptax_current",
                "title": "PTAX atual",
                "value": latest["value"],
                "unit": "R$/US$",
                "detail": market_decimal(fx_30d),
                "detail_label": "30D",
                "source": "BCB",
                "competence": latest["reference_date"],
                "tooltip": "Ultima PTAX venda valida menor ou igual ao corte. Sanity: 0 < PTAX < 20.",
            }
        )
    if period_change is not None and first and latest:
        cards.append(
            {
                "id": "fx_period_change",
                "title": "Variacao cambial no periodo",
                "value": market_decimal(period_change),
                "unit": "%",
                "detail": f"{first['reference_date']} -> {latest['reference_date']}",
                "detail_label": "periodo",
                "source": "BCB",
                "competence": latest["reference_date"],
                "tooltip": "FX_PERIOD_CHANGE = PTAX ultimo dia valido / PTAX primeiro dia valido - 1.",
            }
        )
    if fx_30d is not None:
        cards.append(
            {
                "id": "fx_30d",
                "title": "Variacao 30D",
                "value": market_decimal(fx_30d),
                "unit": "%",
                "detail": "ultimo valido contra dia util proximo de 30 dias antes",
                "detail_label": "30D",
                "source": "BCB",
                "competence": latest["reference_date"] if latest else None,
                "tooltip": "FX_30D = PTAX_latest / PTAX_closest_valid_day_30d_before - 1.",
            }
        )
    if average_value is not None:
        cards.append(
            {
                "id": "fx_average",
                "title": "Media PTAX periodo",
                "value": market_decimal(average_value),
                "unit": "R$/US$",
                "detail": f"{len(ptax_series)} dias validos",
                "detail_label": "media",
                "source": "BCB",
                "competence": latest["reference_date"] if latest else None,
                "tooltip": "Media simples das PTAX validas no periodo selecionado.",
            }
        )

    family_rows: list[dict[str, Any]] = []
    fob_ptax_chart: list[dict[str, Any]] = []
    family_import_chart: list[dict[str, Any]] = []
    pressure_components: list[dict[str, Any]] = []
    decision_readings: list[dict[str, str]] = []

    if comex_status["status"] == "READY":
        cur.execute(
            """
            select
              familia_abr,
              coalesce(sum(toneladas), 0) as tons,
              coalesce(sum(vl_fob_usd), 0) as fob,
              coalesce(sum(vl_frete_usd), 0) as frete,
              coalesce(sum(vl_seguro_usd), 0) as seguro
            from public.fact_steel_import_monthly
            where (%s::date is null or periodo_inicio >= %s::date)
              and (%s::date is null or periodo_inicio <= %s::date)
            group by familia_abr
            having coalesce(sum(toneladas), 0) > 0 and coalesce(sum(vl_fob_usd), 0) > 0
            order by tons desc
            """,
            (date_from, date_from, date_to, date_to),
        )
        for family, tons, fob, freight, insurance in cur.fetchall():
            fob_usd_t = fob / tons if tons else None
            cif_usd_t = (fob + freight + insurance) / tons if tons else None
            family_rows.append(
                {
                    "family": family,
                    "ptax_signal": 1 if period_change is not None and period_change > Decimal("2") else -1 if period_change is not None and period_change < Decimal("-2") else 0,
                    "fob_signal": 0,
                    "import_signal": 0,
                    "stock_signal": 0,
                    "demand_signal": 0,
                    "score": 0,
                    "classification": "MISTA / NEUTRA",
                    "coverage": "1/5",
                    "fob_usd_t": market_decimal(fob_usd_t),
                    "cif_usd_t": market_decimal(cif_usd_t),
                    "tons": market_decimal(tons),
                    "status": "READY",
                }
            )
    else:
        pressure_components.append(
            {
                "component": "Pressao por familia",
                "status": comex_status["status"],
                "message": comex_status["message"],
            }
        )

    return {
        "ptax": {
            "latest": latest,
            "first": first,
            "period_change": market_decimal(period_change),
            "change_30d": market_decimal(fx_30d),
            "average": market_decimal(average_value),
            "series": ptax_series,
            "invalid_values": invalid_values,
        },
        "data_coverage": {
            "requested_from": date_from.isoformat() if date_from else None,
            "requested_to": date_to.isoformat() if date_to else None,
            "available_from": first["reference_date"] if first else None,
            "available_to": latest["reference_date"] if latest else None,
            "valid_days": len(ptax_series),
            "is_partial": bool(date_from and first and first.get("reference_date") and first["reference_date"] > date_from.isoformat()),
            "message": (
                f"PTAX disponivel no banco a partir de {first['reference_date']} para o recorte solicitado."
                if date_from and first and first.get("reference_date") and first["reference_date"] > date_from.isoformat()
                else None
            ),
        },
        "cards": cards,
        "comex_status": comex_status,
        "family_pressure": family_rows,
        "fob_ptax_chart": fob_ptax_chart,
        "family_import_chart": family_import_chart,
        "pressure_components": pressure_components,
        "decision_readings": decision_readings,
    }


def solar_growth_signal(value: Decimal | None) -> int | None:
    if value is None:
        return None
    if value > Decimal("10"):
        return 1
    if value < Decimal("-10"):
        return -1
    return 0


def solar_signal_label(score: int | None) -> str:
    if score is None:
        return "DADOS INSUFICIENTES"
    if score >= 2:
        return "ACELERANDO"
    if score <= -2:
        return "DESACELERANDO"
    return "ESTAVEL / MISTO"


def solar_pct_change(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous == 0:
        return None
    return ((current / previous) - Decimal("1")) * Decimal("100")


def solar_polo_for_row(municipio: str | None, uf: str | None) -> tuple[str, str]:
    if municipio:
        classification = classify_sale(city=municipio, seller=None, segment="VAREJO")
        if classification.canal == "varejo" and classification.regiao:
            return classification.regiao, "municipio_polo_abr"
        if (uf or "").upper() in {"MG", "SP"}:
            return f"ENTORNO {uf.upper()}", "municipio_entorno"
        return "FORA_AREA", "municipio_fora_area"
    if (uf or "").upper() in {"MG", "SP"}:
        return f"UF {uf.upper()} (sem municipio)", "uf_apenas_sem_polo"
    return "FORA_AREA", "uf_fora_area"


def market_solar_summary(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    cur.execute("select max(periodo_inicio) from public.fact_solar_monthly")
    latest_period = cur.fetchone()[0]
    if not latest_period:
        return {}

    cur.execute(
        """
        select periodo_inicio, sum(new_mw), sum(novas_instalacoes)
        from public.fact_solar_monthly
        group by periodo_inicio
        order by periodo_inicio desc
        limit 8
        """,
    )
    recent_months = cur.fetchall()
    period_end = latest_period
    partial_periods: list[str] = []
    if recent_months:
        latest_new = Decimal(str(recent_months[0][1] or 0))
        previous_values = [Decimal(str(row[1] or 0)) for row in recent_months[1:4] if row[1] is not None and Decimal(str(row[1] or 0)) > 0]
        previous_avg = sum(previous_values, Decimal("0")) / Decimal(len(previous_values)) if previous_values else None
        if previous_avg and latest_new < previous_avg * Decimal("0.35"):
            partial_periods.append(latest_period.isoformat())
            cur.execute(
                """
                select max(periodo_inicio)
                from public.fact_solar_monthly
                where periodo_inicio < %s
                """,
                (latest_period,),
            )
            period_end = cur.fetchone()[0] or latest_period

    if date_to:
        requested_month = date(date_to.year, date_to.month, 1)
        if requested_month < period_end:
            period_end = requested_month
    period_from = date(date_from.year, date_from.month, 1) if date_from else add_months(period_end, -23)
    current_12_start = add_months(period_end, -11)
    previous_12_start = add_months(current_12_start, -12)
    previous_12_end = add_months(current_12_start, -1)

    cur.execute(
        """
        select
          sum(new_mw),
          sum(novas_instalacoes)
        from public.fact_solar_monthly
        where periodo_inicio between %s and %s
          and upper(coalesce(uf, '')) in ('MG', 'SP')
        """,
        (current_12_start, period_end),
    )
    current_new_mw, current_installations = cur.fetchone()

    cur.execute(
        """
        select
          sum(new_mw),
          sum(novas_instalacoes)
        from public.fact_solar_monthly
        where periodo_inicio between %s and %s
          and upper(coalesce(uf, '')) in ('MG', 'SP')
        """,
        (previous_12_start, previous_12_end),
    )
    previous_new_mw, previous_installations = cur.fetchone()

    current_new_mw = Decimal(str(current_new_mw or 0))
    previous_new_mw = Decimal(str(previous_new_mw or 0))
    current_installations = int(current_installations or 0)
    previous_installations = int(previous_installations or 0)
    current_avg_kw = (current_new_mw * Decimal("1000") / Decimal(current_installations)) if current_installations else None
    previous_avg_kw = (previous_new_mw * Decimal("1000") / Decimal(previous_installations)) if previous_installations else None
    mw_growth = solar_pct_change(current_new_mw, previous_new_mw)
    installations_growth = solar_pct_change(Decimal(current_installations), Decimal(previous_installations) if previous_installations else None)
    average_kw_growth = solar_pct_change(current_avg_kw, previous_avg_kw)
    signal_components = {
        "mw_growth": {"value": market_decimal(mw_growth), "signal": solar_growth_signal(mw_growth)},
        "installations_growth": {"value": market_decimal(installations_growth), "signal": solar_growth_signal(installations_growth)},
        "average_size_growth": {"value": market_decimal(average_kw_growth), "signal": solar_growth_signal(average_kw_growth)},
    }
    valid_signals = [item["signal"] for item in signal_components.values() if item["signal"] is not None]
    signal_score = sum(valid_signals) if valid_signals else None

    cur.execute(
        """
        select periodo_inicio, sum(new_mw), sum(novas_instalacoes)
        from public.fact_solar_monthly
        where periodo_inicio between %s and %s
          and upper(coalesce(uf, '')) in ('MG', 'SP')
        group by periodo_inicio
        order by periodo_inicio
        """,
        (period_from, period_end),
    )
    raw_monthly = cur.fetchall()
    monthly = []
    for index, row in enumerate(raw_monthly):
        values = [Decimal(str(item[1] or 0)) for item in raw_monthly[max(0, index - 2) : index + 1] if item[1] is not None]
        ma3 = sum(values, Decimal("0")) / Decimal(len(values)) if values else None
        monthly.append(
            {
                "period": row[0].isoformat(),
                "period_label": row[0].strftime("%m/%y"),
                "new_mw": market_decimal(row[1]),
                "new_mw_ma3": market_decimal(ma3),
                "installations": int(row[2] or 0),
                "is_partial_period": row[0].isoformat() in partial_periods,
            }
        )

    cur.execute(
        """
        select periodo_inicio, municipio, uf, classe, sum(new_mw), sum(novas_instalacoes)
        from public.fact_solar_monthly
        where periodo_inicio between %s and %s
          and upper(coalesce(uf, '')) in ('MG', 'SP')
        group by periodo_inicio, municipio, uf, classe
        """,
        (previous_12_start, period_end),
    )
    pole_metrics: dict[str, dict[str, Any]] = {}
    class_metrics: dict[str, dict[str, Any]] = {}
    current_total = Decimal("0")
    for row in cur.fetchall():
        period, municipio, uf, classe, new_mw, installations = row
        new_mw_dec = Decimal(str(new_mw or 0))
        installations_int = int(installations or 0)
        pole, coverage = solar_polo_for_row(municipio, uf)
        item = pole_metrics.setdefault(
            pole,
            {
                "polo": pole,
                "coverage": coverage,
                "current_mw": Decimal("0"),
                "previous_mw": Decimal("0"),
                "current_installations": 0,
                "previous_installations": 0,
                "latest_period": None,
            },
        )
        target_prefix = "current" if current_12_start <= period <= period_end else "previous"
        item[f"{target_prefix}_mw"] += new_mw_dec
        item[f"{target_prefix}_installations"] += installations_int
        if current_12_start <= period <= period_end:
            current_total += new_mw_dec
            item["latest_period"] = max(item["latest_period"] or period, period)
        class_item = class_metrics.setdefault(
            classe or "Sem classe",
            {"classe": classe or "Sem classe", "mw": Decimal("0"), "installations": 0},
        )
        if current_12_start <= period <= period_end:
            class_item["mw"] += new_mw_dec
            class_item["installations"] += installations_int

    radar_rows = []
    accelerating_poles = 0
    for item in pole_metrics.values():
        avg_kw = (item["current_mw"] * Decimal("1000") / Decimal(item["current_installations"])) if item["current_installations"] else None
        growth = solar_pct_change(item["current_mw"], item["previous_mw"])
        inst_growth = solar_pct_change(Decimal(item["current_installations"]), Decimal(item["previous_installations"]) if item["previous_installations"] else None)
        signal = solar_signal_label(sum(signal for signal in (solar_growth_signal(growth), solar_growth_signal(inst_growth)) if signal is not None))
        if growth is not None and growth > Decimal("10") and item["current_mw"] >= Decimal("1"):
            accelerating_poles += 1
        radar_rows.append(
            {
                "polo": item["polo"],
                "new_mw_12m": market_decimal(item["current_mw"]),
                "mw_yoy": market_decimal(growth),
                "installations_12m": item["current_installations"],
                "installations_yoy": market_decimal(inst_growth),
                "average_kw_per_installation": market_decimal(avg_kw),
                "share": market_decimal((item["current_mw"] / current_total * Decimal("100")) if current_total else None),
                "signal": signal,
                "coverage": item["coverage"],
                "latest_period": item["latest_period"].isoformat() if item["latest_period"] else None,
            }
        )
    radar_rows.sort(key=lambda item: Decimal(str(item["new_mw_12m"] or "0")), reverse=True)
    leader = radar_rows[0] if radar_rows else None
    scatter = [
        {
            "polo": item["polo"],
            "new_mw_12m": item["new_mw_12m"],
            "mw_yoy": item["mw_yoy"],
            "installations_12m": item["installations_12m"],
            "signal": item["signal"],
        }
        for item in radar_rows
    ]
    classes = [
        {
            "class": item["classe"],
            "new_mw_12m": market_decimal(item["mw"]),
            "installations_12m": item["installations"],
            "average_kw_per_installation": market_decimal((item["mw"] * Decimal("1000") / Decimal(item["installations"])) if item["installations"] else None),
        }
        for item in sorted(class_metrics.values(), key=lambda value: value["mw"], reverse=True)
    ]
    readings = solar_readings(radar_rows, classes, signal_components)
    return {
        "latest_period": period_end.isoformat(),
        "last_complete_month": period_end.isoformat(),
        "partial_periods": partial_periods,
        "unit_metadata": {
            "field_name": "MdaPotenciaInstaladaKW",
            "raw_unit": "kW",
            "normalized_unit": "MW",
            "scale_factor": "0.001",
            "source_resource": "ANEEL relacao-de-empreendimentos-de-geracao-distribuida / empreendimento-geracao-distribuida.parquet",
            "validated_at": date.today().isoformat(),
        },
        "kpis": {
            "last_12_new_mw": market_decimal(current_new_mw),
            "last_12_installations": current_installations,
            "average_kw_per_installation": market_decimal(current_avg_kw),
            "mw_growth_yoy": market_decimal(mw_growth),
            "leader_pole": leader["polo"] if leader else None,
            "leader_pole_mw": leader["new_mw_12m"] if leader else None,
            "leader_pole_yoy": leader["mw_yoy"] if leader else None,
            "accelerating_poles": accelerating_poles,
        },
        "signal": {
            "label": solar_signal_label(signal_score),
            "score": signal_score,
            "components": signal_components,
        },
        "monthly": monthly,
        "radar_by_pole": radar_rows,
        "scatter": scatter,
        "classes": classes,
        "readings": readings,
        "quality": {
            "message": "Solar e radar setorial indireto; nao converte MW em demanda fisica de aco.",
            "coverage": "municipio" if any(item["coverage"].startswith("municipio") for item in radar_rows) else "uf_apenas",
            "sanity_status": "VALID" if current_new_mw < Decimal("100000") else "INVALID",
        },
    }


def solar_readings(
    radar_rows: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    signal_components: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    readings: list[dict[str, str]] = []
    if radar_rows:
        leader = radar_rows[0]
        readings.append(
            {
                "key": "leader",
                "severity": "neutral",
                "text": f"{leader['polo']} concentra {market_decimal(leader.get('share'))}% dos MW novos do recorte, com {market_decimal(leader.get('new_mw_12m'))} MW em 12M.",
            }
        )
    growing = [row for row in radar_rows if row.get("mw_yoy") is not None and Decimal(str(row["mw_yoy"])) > Decimal("10")]
    if growing:
        readings.append(
            {
                "key": "growth",
                "severity": "positive",
                "text": f"{len(growing)} regioes/polos mostram crescimento de MW acima de 10% na janela 12M.",
            }
        )
    if classes:
        top_class = classes[0]
        readings.append(
            {
                "key": "class",
                "severity": "neutral",
                "text": f"{top_class['class']} lidera o recorte solar por MW novos; use como sinal de perfil, nao como demanda garantida de aco.",
            }
        )
    score_parts = [item.get("signal") for item in signal_components.values() if item.get("signal") is not None]
    positives = len([item for item in score_parts if item == 1])
    negatives = len([item for item in score_parts if item == -1])
    readings.append(
        {
            "key": "signal",
            "severity": "attention" if negatives > positives else "neutral",
            "text": f"Sinal 12M calculado por MW, instalacoes e porte medio: {positives} positivos e {negatives} negativos.",
        }
    )
    return readings[:4]


def market_obrasgov_summary(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        select
          coalesce(sum(projetos), 0),
          coalesce(sum(investimento_previsto), 0),
          coalesce(sum(empregos_gerados), 0)
        from public.fact_obrasgov_investments
        """
    )
    projetos, investimento, empregos = cur.fetchone()

    cur.execute(
        """
        select uf, coalesce(sum(projetos), 0), coalesce(sum(investimento_previsto), 0)
        from public.fact_obrasgov_investments
        group by uf
        order by sum(investimento_previsto) desc nulls last
        limit 10
        """
    )
    top_regions = [
        {
            "uf": row[0],
            "projects": row[1] or 0,
            "investment": market_decimal(row[2]),
        }
        for row in cur.fetchall()
    ]
    return {
        "kpis": {
            "projects": int(projetos or 0),
            "investment": market_decimal(investimento),
            "jobs": market_decimal(empregos),
        },
        "top_regions": top_regions,
    }


OPPORTUNITY_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("estrutura metalica", 5),
    ("estrutura em aco", 5),
    ("cobertura metalica", 5),
    ("telha metalica", 5),
    ("telha de aco", 5),
    ("perfil metalico", 5),
    ("perfil de aco", 5),
    ("tubo de aco", 5),
    ("metalon", 5),
    ("chapa de aco", 5),
    ("galpao metalico", 5),
    ("galpao", 4),
    ("pavilhao metalico", 4),
    ("mezanino metalico", 4),
    ("estrutura de cobertura", 4),
    ("cobertura industrial", 4),
    ("serralheria estrutural", 4),
    ("serralheria", 3),
    ("esquadria metalica", 3),
    ("guarda-corpo", 3),
    ("corrimao", 3),
    ("gradil", 3),
    ("portao metalico", 3),
    ("alambrado", 3),
    ("ferragem", 2),
    ("estrutura", 2),
    ("cobertura", 2),
    ("metalurgica", 2),
    ("aco", 1),
    ("construcao", 1),
    ("reforma", 1),
)

OPPORTUNITY_NEGATIVE_KEYWORDS = (
    "software",
    "medicamento",
    "alimentacao",
    "servicos administrativos",
    "consultoria",
    "locacao de veiculos",
    "material escolar",
    "equipamento medico",
    "material hospitalar",
)

OPPORTUNITY_POLE_ALIASES: dict[str, str] = {
    "braganca paulista": "BRAGANCA",
    "braganca": "BRAGANCA",
    "jundiai": "JUNDIAI",
    "varginha": "VARGINHA",
    "pouso alegre": "POUSO ALEGRE",
    "pocos de caldas": "POCOS DE CALDAS",
    "ituba": "ITAJUBA",
    "itajuba": "ITAJUBA",
    "extrema": "EXTREMA",
    "cambui": "CAMBUI",
}


def opportunity_text(value: str | None) -> str:
    return market_ascii(value or "").replace("ç", "c")


def opportunity_keyword_matches(text: str) -> tuple[int, list[str], bool]:
    normalized = opportunity_text(text)
    if any(opportunity_text(term) in normalized for term in OPPORTUNITY_NEGATIVE_KEYWORDS):
        return 0, [], True
    score = 0
    matches: list[str] = []
    for term, weight in OPPORTUNITY_KEYWORDS:
        normalized_term = opportunity_text(term)
        if normalized_term in normalized:
            score += weight
            matches.append(term)
    generic_only = matches and all(opportunity_text(term) in {"aco", "construcao", "reforma"} for term in matches)
    if generic_only:
        score = min(score, 2)
    return score, sorted(set(matches)), False


def opportunity_product_match(matches: list[str]) -> list[str]:
    products: set[str] = set()
    normalized = {opportunity_text(term) for term in matches}
    if normalized & {"cobertura metalica"}:
        products.update(["TELHAS", "PERFIS", "TUBOS / METALONS"])
    if normalized & {"telha metalica", "telha de aco"}:
        products.add("TELHAS")
    if normalized & {"estrutura metalica", "estrutura em aco"}:
        products.update(["PERFIS", "TUBOS / METALONS", "CHAPAS"])
    if normalized & {"galpao metalico", "galpao"}:
        products.update(["TELHAS", "PERFIS", "TUBOS / METALONS", "CHAPAS"])
    if normalized & {"serralheria", "serralheria estrutural"}:
        products.update(["TUBOS / METALONS", "PERFIS", "CHAPAS"])
    if normalized & {"gradil", "portao metalico"}:
        products.update(["TUBOS / METALONS", "PERFIS"])
    if normalized & {"guarda-corpo", "corrimao", "alambrado", "tubo de aco", "metalon"}:
        products.add("TUBOS / METALONS")
    if normalized & {"mezanino metalico", "perfil metalico", "perfil de aco"}:
        products.add("PERFIS")
    if normalized & {"chapa de aco"}:
        products.add("CHAPAS")
    return sorted(products)


def opportunity_portfolio_score(keyword_score: int, matches: list[str], irrelevant: bool) -> int:
    if irrelevant or keyword_score <= 0:
        return 0
    specific = [term for term in matches if opportunity_text(term) not in {"aco", "construcao", "reforma"}]
    high_fit_terms = {opportunity_text(source) for source, weight in OPPORTUNITY_KEYWORDS if weight == 5}
    if any(opportunity_text(term) in high_fit_terms for term in specific):
        return 40
    if keyword_score >= 6 and specific:
        return 30
    if keyword_score >= 3 and specific:
        return 20
    return 10


def opportunity_territory(municipality: str | None, uf: str | None) -> dict[str, str]:
    normalized_city = opportunity_text(municipality)
    polo = OPPORTUNITY_POLE_ALIASES.get(normalized_city)
    if polo:
        return {"territory_class": "TERRITORIO_ATUAL_ABR", "polo_abr": polo, "route_match": municipality or polo}
    if (uf or "").upper() in {"MG", "SP"}:
        return {"territory_class": "EXPANSAO_ENTORNO_ESTRATEGICO", "polo_abr": "ENTORNO", "route_match": uf or ""}
    return {"territory_class": "FORA_AREA", "polo_abr": "FORA_AREA", "route_match": uf or ""}


def opportunity_recency_score(published_at: date | None, date_to: date | None) -> int:
    if not published_at:
        return 0
    reference = date_to or date.today()
    days = (reference - published_at).days
    if days <= 30:
        return 10
    if days <= 60:
        return 7
    if days <= 90:
        return 5
    if days <= 180:
        return 2
    return 0


def opportunity_size_score(value: Decimal | None) -> int:
    if value is None:
        return 0
    if value >= Decimal("10000000"):
        return 10
    if value >= Decimal("5000000"):
        return 8
    if value >= Decimal("1000000"):
        return 6
    if value >= Decimal("250000"):
        return 4
    return 2


def opportunity_priority_label(score: int) -> str:
    if score >= 70:
        return "ALTA PRIORIDADE"
    if score >= 50:
        return "MEDIA PRIORIDADE"
    if score >= 30:
        return "BAIXA PRIORIDADE"
    return "MONITORAR / DESCARTAR"


def opportunity_fingerprint(municipality: str, agency: str, object_text: str, value: Decimal | None, published_at: date | None) -> str:
    value_band = "sem_valor"
    if value is not None:
        if value >= Decimal("10000000"):
            value_band = "10m_plus"
        elif value >= Decimal("1000000"):
            value_band = "1m_10m"
        elif value >= Decimal("250000"):
            value_band = "250k_1m"
        else:
            value_band = "ate_250k"
    period = published_at.strftime("%Y-%m") if published_at else "sem_data"
    base = "|".join([opportunity_text(municipality), opportunity_text(agency), opportunity_text(object_text)[:120], value_band, period])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def market_opportunities_summary(
    cur: Any,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    reference_to = date_to or date.today()
    reference_from = date_from or reference_to - timedelta(days=90)
    try:
        cur.execute(
            """
            select count(*), count(*) filter (
              where pncp_id is not null
                and coalesce(objeto, '') <> ''
                and coalesce(municipio, uf, '') <> ''
                and data_publicacao is not null
            )
            from public.fact_pncp_opportunities
            """
        )
        raw_pncp_count, detail_sufficient_count = cur.fetchone()

        cur.execute(
            """
            select data_publicacao, coalesce(uf, ''), coalesce(municipio, ''), coalesce(orgao, ''),
                   coalesce(objeto, ''), valor_estimado, relevance_score, pncp_id, termos_encontrados
            from public.fact_pncp_opportunities
            where data_publicacao >= %s::date
              and data_publicacao <= %s::date
            order by data_publicacao desc nulls last
            limit 500
            """
            ,
            (reference_from, reference_to),
        )
        classified = []
        fingerprints: set[str] = set()
        duplicates = 0
        for row in cur.fetchall():
            published_at, uf, municipality, agency, object_text, value, _relevance_score, external_id, _terms = row
            if not external_id or not object_text or not (municipality or uf) or not published_at:
                continue
            fingerprint = opportunity_fingerprint(municipality, agency, object_text, value, published_at)
            if fingerprint in fingerprints:
                duplicates += 1
                continue
            fingerprints.add(fingerprint)
            keyword_score, matches, irrelevant = opportunity_keyword_matches(object_text)
            products = opportunity_product_match(matches)
            territory = opportunity_territory(municipality, uf)
            portfolio_score = opportunity_portfolio_score(keyword_score, matches, irrelevant)
            territory_score = 20 if territory["territory_class"] == "TERRITORIO_ATUAL_ABR" else 10 if territory["territory_class"] == "EXPANSAO_ENTORNO_ESTRATEGICO" else 0
            timing_score = 15
            recency_score = opportunity_recency_score(published_at, reference_to)
            size_score = opportunity_size_score(value)
            priority_score = portfolio_score + territory_score + timing_score + recency_score + size_score
            if territory["territory_class"] == "FORA_AREA":
                priority_score = min(priority_score, 29)
            classified.append(
                {
                    "opportunity_id": external_id,
                    "fingerprint": fingerprint,
                    "source_type": "PNCP",
                    "date": published_at.isoformat(),
                    "uf": uf,
                    "municipality": municipality,
                    "agency": agency,
                    "object": object_text,
                    "value": market_decimal(value),
                    "status": "PUBLICADA",
                    "deadline": None,
                    "link": "",
                    "territory_class": territory["territory_class"],
                    "polo_abr": territory["polo_abr"],
                    "route_match": territory["route_match"],
                    "keyword_score": keyword_score,
                    "matches": matches,
                    "product_match": products,
                    "priority_score": priority_score,
                    "priority": opportunity_priority_label(priority_score),
                    "commercial_status": "NOVO",
                    "score_components": {
                        "portfolio_fit": portfolio_score,
                        "territory": territory_score,
                        "timing": timing_score,
                        "recency": recency_score,
                        "project_size": size_score,
                    },
                    "score_reasons": matches + [territory["polo_abr"], f"publicado ha {(reference_to - published_at).days} dias"],
                }
            )
        relevant = [item for item in classified if item["territory_class"] != "FORA_AREA" and item["priority_score"] >= 30]
        relevant.sort(key=lambda item: (item["priority_score"], item["date"], Decimal(str(item["value"] or "0"))), reverse=True)

        by_pole: dict[str, dict[str, Any]] = {}
        by_family: dict[str, int] = defaultdict(int)
        by_month: dict[str, dict[str, int]] = {}
        scatter = []
        for item in relevant:
            pole = item["polo_abr"]
            by_pole.setdefault(pole, {"polo": pole, "high": 0, "medium": 0, "low": 0, "total": 0})
            by_pole[pole]["total"] += 1
            if item["priority_score"] >= 70:
                by_pole[pole]["high"] += 1
            elif item["priority_score"] >= 50:
                by_pole[pole]["medium"] += 1
            else:
                by_pole[pole]["low"] += 1
            for family in item["product_match"]:
                by_family[family] += 1
            month = item["date"][:7]
            by_month.setdefault(month, {"period": month, "period_label": month, "high": 0, "medium": 0, "total": 0})
            by_month[month]["total"] += 1
            if item["priority_score"] >= 70:
                by_month[month]["high"] += 1
            elif item["priority_score"] >= 50:
                by_month[month]["medium"] += 1
            scatter.append(
                {
                    "id": item["opportunity_id"],
                    "polo": item["polo_abr"],
                    "municipality": item["municipality"],
                    "object": item["object"],
                    "value": item["value"],
                    "priority_score": item["priority_score"],
                    "product_match": item["product_match"],
                }
            )

        obras = market_obrasgov_summary(cur)
        raw_obras_count = int(obras.get("kpis", {}).get("projects") or 0)
        total_value = sum((Decimal(str(item["value"])) for item in relevant if item.get("value")), Decimal("0"))
        recent_30 = len([item for item in relevant if item.get("date") and (reference_to - date.fromisoformat(item["date"])).days <= 30])
        return {
            "source": "classified_public_opportunities",
            "source_types": ["PNCP", "OBRASGOV"],
            "kpis": {
                "opportunities": len(relevant),
                "high_relevance": len([item for item in relevant if item["priority_score"] >= 70]),
                "total_value": market_decimal(total_value),
                "regions": len({item["polo_abr"] for item in relevant}),
                "new_30d": recent_30,
                "deadlines_soon": 0,
            },
            "raw_counts": {
                "pncp_raw": int(raw_pncp_count or 0),
                "obrasgov_raw_projects": raw_obras_count,
                "detail_sufficient": int(detail_sufficient_count or 0),
                "classified": len(classified),
                "relevant": len(relevant),
                "duplicates": duplicates,
                "insufficient_detail": max(raw_obras_count - int(detail_sufficient_count or 0), 0) if raw_obras_count else 0,
            },
            "top_regions": sorted(by_pole.values(), key=lambda item: (item["high"], item["medium"], item["total"]), reverse=True),
            "families": [{"family": key, "opportunities": value} for key, value in sorted(by_family.items(), key=lambda item: item[1], reverse=True)],
            "scatter": scatter[:40],
            "monthly": [by_month[key] for key in sorted(by_month)],
            "detail": relevant[:30],
            "readings": opportunity_readings(relevant),
            "quality": {
                "message": "ObrasGov disponivel apenas agregado nesta carga; nao entra na fila comercial sem objeto/municipio/data por projeto.",
                "minimum_fields": ["ID", "Fonte", "Objeto/descricao", "Municipio ou UF", "Data"],
            },
        }
    except Exception:
        pass
    return {}


def opportunity_readings(relevant: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not relevant:
        return [{"key": "no_classified", "severity": "attention", "text": "Nenhuma oportunidade comercial classificada no recorte; registros agregados sem detalhe nao entram na fila."}]
    readings = []
    high = [item for item in relevant if item["priority_score"] >= 70]
    if high:
        top_pole = max({item["polo_abr"] for item in high}, key=lambda pole: len([item for item in high if item["polo_abr"] == pole]))
        readings.append({"key": "high_pole", "severity": "positive", "text": f"{len(high)} oportunidades de alta prioridade; maior concentracao em {top_pole}."})
    product_counts: dict[str, int] = defaultdict(int)
    for item in relevant:
        for product in item["product_match"]:
            product_counts[product] += 1
    if product_counts:
        leaders = sorted(product_counts.items(), key=lambda item: item[1], reverse=True)[:2]
        readings.append({"key": "products", "severity": "neutral", "text": " e ".join(product for product, _count in leaders) + f" aparecem em {sum(count for _product, count in leaders)} oportunidades relevantes."})
    return readings[:4]


def market_summary(
    *,
    market_tab: str | None = None,
    market_date_from: date | None = None,
    market_date_to: date | None = None,
) -> dict[str, Any]:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            sources = market_registry_rows(cur)
            filter_defaults = market_filter_defaults(cur)
            decision_layer = market_decision_layer(cur, date_to=market_date_to)
            healthy = {
                row["source_key"]
                for row in sources
                if row["status"] == "HEALTHY" and row["configured"] and row["reachable"] and row["last_row_count"] > 0
            }

            steel_sources = [key for key in ("aco_brasil_estatistica_mensal", "inda_estatisticas") if key in healthy]
            construction_sources = [key for key in ("ibge_construcao_sidra", "cni_sondagem_construcao") if key in healthy]
            industry_sources = [key for key in ("ibge_pim_sidra", "cni_sondagem_industrial") if key in healthy]

            steel_indicators = market_latest_indicators(cur, steel_sources, limit=16)
            construction_indicators = market_latest_indicators(cur, construction_sources, limit=16)
            industry_indicators = market_latest_indicators(cur, industry_sources, limit=16)
            macro_indicators = market_latest_indicators(cur, ["world_bank_wdi"] if "world_bank_wdi" in healthy else [], limit=8)
            overview_decision = market_overview_decision(
                cur,
                date_from=market_date_from,
                date_to=market_date_to,
            )
            steel_decision = market_steel_decision(
                cur,
                date_from=market_date_from,
                date_to=market_date_to,
            )
            industry_decision = market_industry_decision(
                cur,
                date_from=market_date_from,
                date_to=market_date_to,
            )
            construction_decision = market_construction_decision(
                cur,
                date_from=market_date_from,
                date_to=market_date_to,
            )

            steel_series = market_indicator_series(cur, "aco_brasil_estatistica_mensal", "aco_brasil_consumo_aparente_total")
            industry_series = market_indicator_series(cur, "cni_sondagem_industrial", "cni_industria_expectativa_demanda")
            construction_series = market_indicator_series(cur, "ibge_construcao_sidra", "ibge_construcao_indice")

            comex = market_comex_summary(cur) if "comex_stat_ncm" in healthy else {}
            ptax = market_ptax_summary(cur) if "bcb_dolar_ptax" in healthy else {}
            prices_decision = market_prices_decision(cur, date_from=market_date_from, date_to=market_date_to)
            solar = (
                market_solar_summary(cur, date_from=market_date_from, date_to=market_date_to)
                if "aneel_dados_abertos" in healthy
                else {}
            )
            public_works = market_obrasgov_summary(cur) if "obrasgov_projetos" in healthy else {}
            opportunities = (
                market_opportunities_summary(cur, date_from=market_date_from, date_to=market_date_to)
                if healthy & {"pncp_consulta", "obrasgov_projetos"}
                else {}
            )

            tab_rules = [
                ("market-overview", True),
                ("steel-market", bool(steel_sources)),
                ("market-prices", bool(comex or ptax)),
                ("imports", bool(comex)),
                ("industry", bool(industry_sources)),
                ("construction", bool(construction_sources or public_works)),
                ("regional", False),
                ("competition", False),
                ("opportunities", bool(opportunities)),
                ("solar", bool(solar)),
            ]
            available_tabs = [key for key, enabled in tab_rules if enabled]

    return {
        "sources": sources,
        "active_filter": {
            "tab": market_tab,
            "date_from": market_date_from.isoformat() if market_date_from else None,
            "date_to": market_date_to.isoformat() if market_date_to else None,
        },
        "filter_defaults": filter_defaults,
        "decision_layer": decision_layer,
        "healthy_sources": sorted(healthy),
        "available_tabs": available_tabs,
        "overview": {
            "healthy_count": len(healthy),
            "configured_count": len([row for row in sources if row["configured"]]),
            "error_count": len([row for row in sources if row["status"] == "ERROR"]),
            "latest_periods": [
                {
                    "source_key": row["source_key"],
                    "source_name": row["source_name"],
                    "period": row["latest_reference_period"],
                    "rows": row["last_row_count"],
                    "status": row["status"],
                }
                for row in sources
                if row["status"] == "HEALTHY"
            ],
            "macro_indicators": macro_indicators,
        },
        "overview_decision": overview_decision,
        "steel_market": {
            "indicators": steel_indicators,
            "series": steel_series,
            "decision": steel_decision,
        },
        "construction": {
            "indicators": construction_indicators,
            "series": construction_series,
            "public_works": public_works,
            "decision": construction_decision,
        },
        "prices": {
            "ptax": ptax,
            "comex": comex,
            "decision": prices_decision,
        },
        "imports": comex,
        "industry": {
            "indicators": industry_indicators,
            "series": industry_series,
            "decision": industry_decision,
        },
        "opportunities": opportunities,
        "solar": solar,
    }


def drive_spreadsheet_dashboard_cache() -> dict[str, Any]:
    env = load_env()
    try:
        with connect_database(env) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select detected_type, drive_file_name, drive_modified_time, row_count, payload, refreshed_at
                    from public.dashboard_drive_spreadsheet_cache
                    order by detected_type, drive_modified_time desc nulls last, refreshed_at desc
                    """
                )
                rows = cur.fetchall()
    except Exception:
        return {"available": False, "latest_by_type": {}, "history": []}

    latest_by_type: dict[str, dict[str, Any]] = {}
    history: list[dict[str, Any]] = []
    for detected_type, file_name, modified_time, row_count, payload, refreshed_at in rows:
        item = {
            "detected_type": detected_type,
            "drive_file_name": file_name,
            "drive_modified_time": modified_time.isoformat() if modified_time else None,
            "row_count": row_count,
            "payload": payload if isinstance(payload, dict) else {},
            "refreshed_at": refreshed_at.isoformat() if refreshed_at else None,
        }
        history.append(item)
        latest_by_type.setdefault(str(detected_type), item)

    return {
        "available": bool(latest_by_type),
        "latest_by_type": latest_by_type,
        "history": history[:20],
    }


def internal_dashboard_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    *,
    include_sales_regions: bool = False,
    market_tab: str | None = None,
    market_date_from: date | None = None,
    market_date_to: date | None = None,
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
    drive_spreadsheets: dict[str, Any] = {"available": False, "latest_by_type": {}, "history": []}
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
    try:
        drive_spreadsheets = drive_spreadsheet_dashboard_cache()
    except BaseException as exc:
        warnings.append(f"Resumo de planilhas do Drive indisponivel: {type(exc).__name__}: {str(exc)[:160]}")

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
    attendance: dict[str, Any] = {}
    try:
        attendance = attendance_summary(date_from=date_from, date_to=date_to)
        if not attendance.get("data_available"):
            warnings.append(str(attendance.get("message", "Dados de atendimento ainda sem granularidade suficiente.")))
    except BaseException as exc:
        warnings.append(f"Resumo de atendimento indisponivel: {type(exc).__name__}: {str(exc)[:160]}")
    market: dict[str, Any] = {}
    try:
        market = market_summary(
            market_tab=market_tab,
            market_date_from=market_date_from,
            market_date_to=market_date_to,
        )
    except BaseException as exc:
        warnings.append(f"Resumo de mercado indisponivel: {type(exc).__name__}: {str(exc)[:160]}")

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
        "drive_spreadsheets": drive_spreadsheets,
        "recent_history": history,
        "sales_summary": sales_summary,
        "attendance_summary": attendance,
        "market_summary": market,
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
            where_clauses: list[str] = []
            params: list[Any] = []
            if date_from:
                where_clauses.append("sale_date >= %s")
                params.append(date_from)
            if date_to:
                where_clauses.append("sale_date <= %s")
                params.append(date_to)
            where_sql = f"where {' and '.join(where_clauses)}" if where_clauses else ""
            cur.execute(
                f"""
                select
                  cidade,
                  vendedor,
                  segmento,
                  valor_total
                from public.dashboard_sales_fact
                {where_sql}
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
