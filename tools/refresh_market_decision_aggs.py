from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


FAMILIES = ("CHAPAS", "TUBOS / METALONS", "PERFIS", "TELHAS")
COMEX_TO_DECISION_FAMILY = {
    "CHAPA FQ": "CHAPAS",
    "CHAPA FF": "CHAPAS",
    "GALVANIZADA": "CHAPAS",
    "CHAPA GROSSA": "CHAPAS",
    "TUBOS": "TUBOS / METALONS",
    "PERFIS": "PERFIS",
}


@dataclass
class Driver:
    name: str
    value: Decimal | None
    signal: int | None
    source: str
    period: str | None


def as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def pct_change(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - Decimal("1")) * Decimal("100")


def signal_from_pct(change: Decimal | None, threshold: Decimal = Decimal("2")) -> int | None:
    if change is None:
        return None
    if change > threshold:
        return 1
    if change < -threshold:
        return -1
    return 0


def inverse_supply_signal(change: Decimal | None, threshold: Decimal = Decimal("10")) -> int | None:
    if change is None:
        return None
    if change > threshold:
        return -1
    if change < -threshold:
        return 1
    return 0


def cni_signal(value: Decimal | None) -> int | None:
    if value is None:
        return None
    if value > Decimal("52"):
        return 1
    if value < Decimal("48"):
        return -1
    return 0


def classify_score(score: int | None, available: int, positive_label: str, negative_label: str) -> tuple[str, str]:
    if available < 3 or score is None:
        return "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"
    if score >= 2:
        return positive_label, "OK"
    if score <= -2:
        return negative_label, "OK"
    return "MISTA / NEUTRA", "OK"


def fetch_monthly_indicator(cur: Any, source_key: str, indicator_key: str) -> dict[date, Decimal]:
    cur.execute(
        """
        select date_trunc('month', periodo_inicio)::date as periodo, avg(valor) as valor
        from public.mercado_indicadores
        where source_key = %s
          and indicador_key = %s
          and valor is not null
        group by 1
        order by 1
        """,
        (source_key, indicator_key),
    )
    return {row[0]: as_decimal(row[1]) for row in cur.fetchall()}


def latest_driver_from_patterns(cur: Any, source_key: str, patterns: tuple[str, ...], period: date) -> Driver | None:
    clauses = " or ".join(["indicador_key ilike %s or indicador_nome ilike %s" for _ in patterns])
    params: list[Any] = []
    for pattern in patterns:
        params.extend([f"%{pattern}%", f"%{pattern}%"])
    cur.execute(
        f"""
        select indicador_nome, valor, periodo_label, source_key
        from public.mercado_indicadores
        where source_key = %s
          and periodo_inicio <= %s
          and valor is not null
          and ({clauses})
        order by periodo_inicio desc nulls last, coletado_em desc
        limit 1
        """,
        [source_key, period, *params],
    )
    row = cur.fetchone()
    if not row:
        return None
    value = as_decimal(row[1])
    return Driver(row[0], value, cni_signal(value), row[3], row[2])


def upsert_price_pressure(cur: Any) -> int:
    ptax = fetch_monthly_indicator(cur, "bcb_dolar_ptax", "bcb_ptax_cotacaoVenda")
    consumption = fetch_monthly_indicator(cur, "aco_brasil_estatistica_mensal", "aco_brasil_consumo_aparente_total")
    cur.execute("select max(periodo_inicio) from public.mercado_indicadores")
    latest = cur.fetchone()[0]
    if not latest:
        return 0
    period = month_start(latest)

    previous_month = date(period.year - 1, period.month, 1) if period.year > 1 else None
    rows = []
    for family in FAMILIES:
        fx_change = pct_change(ptax.get(period), ptax.get(previous_month)) if previous_month else None
        fx_signal = signal_from_pct(fx_change)

        demand_change = pct_change(consumption.get(period), consumption.get(previous_month)) if previous_month else None
        demand_signal = signal_from_pct(demand_change, Decimal("3"))

        cur.execute(
            """
            with current_3m as (
              select coalesce(sum(toneladas), 0) tons, coalesce(sum(vl_fob_usd), 0) fob
              from public.fact_steel_import_monthly
              where periodo_inicio between (%s::date - interval '2 months') and %s::date
                and familia_abr = any(%s)
            ),
            previous_3m as (
              select coalesce(sum(toneladas), 0) tons, coalesce(sum(vl_fob_usd), 0) fob
              from public.fact_steel_import_monthly
              where periodo_inicio between (%s::date - interval '1 year' - interval '2 months') and (%s::date - interval '1 year')
                and familia_abr = any(%s)
            )
            select current_3m.tons, current_3m.fob, previous_3m.tons, previous_3m.fob
            from current_3m, previous_3m
            """,
            (
                period,
                period,
                [key for key, value in COMEX_TO_DECISION_FAMILY.items() if value == family],
                period,
                period,
                [key for key, value in COMEX_TO_DECISION_FAMILY.items() if value == family],
            ),
        )
        tons_now, fob_now, tons_prev, fob_prev = [as_decimal(item) for item in cur.fetchone()]
        import_change = pct_change(tons_now, tons_prev)
        import_signal = inverse_supply_signal(import_change)
        fob_now_t = fob_now / tons_now if tons_now and tons_now != 0 else None
        fob_prev_t = fob_prev / tons_prev if tons_prev and tons_prev != 0 else None
        fob_signal = signal_from_pct(pct_change(fob_now_t, fob_prev_t))

        inda = latest_driver_from_patterns(cur, "inda_estatisticas", ("estoque",), period)
        inda_signal = -inda.signal if inda and inda.signal is not None else None

        signals = [fx_signal, fob_signal, import_signal, inda_signal, demand_signal]
        available = len([item for item in signals if item is not None])
        score = sum(item for item in signals if item is not None) if available else None
        classification, status = classify_score(score, available, "PRESSAO DE ALTA", "PRESSAO DE BAIXA")
        components = {
            "fx_change_pct": str(fx_change) if fx_change is not None else None,
            "fob_usd_t": str(fob_now_t) if fob_now_t is not None else None,
            "import_3m_yoy_pct": str(import_change) if import_change is not None else None,
            "inda_stock_signal": inda_signal,
            "demand_yoy_pct": str(demand_change) if demand_change is not None else None,
        }
        rows.append((period, family, fx_signal, fob_signal, import_signal, inda_signal, demand_signal, score, classification, available, status, components))

    cur.executemany(
        """
        insert into public.agg_market_price_pressure(
          periodo_inicio, family, fx_signal, fob_signal, import_signal, inda_signal,
          demand_signal, score, classification, available_components_count, status,
          components, source_periods, refreshed_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
        on conflict (periodo_inicio, family)
        do update set
          fx_signal = excluded.fx_signal,
          fob_signal = excluded.fob_signal,
          import_signal = excluded.import_signal,
          inda_signal = excluded.inda_signal,
          demand_signal = excluded.demand_signal,
          score = excluded.score,
          classification = excluded.classification,
          available_components_count = excluded.available_components_count,
          status = excluded.status,
          components = excluded.components,
          source_periods = excluded.source_periods,
          refreshed_at = now()
        """,
        [
            (
                *row[:-1],
                json.dumps(row[-1], ensure_ascii=False),
                json.dumps({"period": period.isoformat()}, ensure_ascii=False),
            )
            for row in rows
        ],
    )
    return len(rows)


def demand_drivers(cur: Any, family: str, period: date) -> list[Driver]:
    drivers: list[Driver] = []
    for source, patterns in (
        ("ibge_pim_sidra", ("produto", "metal", "metalurgia", "maquina")),
        ("cni_sondagem_industrial", ("demanda", "compras", "producao")),
        ("ibge_construcao_sidra", ("construcao",)),
        ("cni_sondagem_construcao", ("atividade", "insumos", "empreendimentos")),
    ):
        driver = latest_driver_from_patterns(cur, source, patterns, period)
        if driver:
            drivers.append(driver)
    if family == "CHAPAS":
        return [item for item in drivers if item.source in {"ibge_pim_sidra", "cni_sondagem_industrial"}]
    if family in {"PERFIS", "TELHAS"}:
        return [item for item in drivers if item.source in {"ibge_construcao_sidra", "cni_sondagem_construcao"}]
    return drivers


def upsert_demand_family(cur: Any) -> int:
    cur.execute("select max(periodo_inicio) from public.mercado_indicadores")
    latest = cur.fetchone()[0]
    if not latest:
        return 0
    period = month_start(latest)
    rows = []
    for family in FAMILIES:
        drivers = demand_drivers(cur, family, period)
        signals = [item.signal for item in drivers if item.signal is not None]
        available = len(signals)
        score = sum(signals) if available else None
        if available < 3 or score is None:
            classification, status = "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"
        elif score >= 2:
            classification, status = "ACELERANDO", "OK"
        elif score <= -2:
            classification, status = "DESACELERANDO", "OK"
        else:
            classification, status = "ESTAVEL / MISTO", "OK"
        payload = [
            {
                "name": item.name,
                "value": str(item.value) if item.value is not None else None,
                "signal": item.signal,
                "source": item.source,
                "period": item.period,
            }
            for item in drivers
        ]
        rows.append((period, family, score, classification, available, status, payload))

    cur.executemany(
        """
        insert into public.agg_market_demand_family(
          periodo_inicio, family, score, classification, available_components_count,
          status, drivers, source_periods, refreshed_at
        )
        values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
        on conflict (periodo_inicio, family)
        do update set
          score = excluded.score,
          classification = excluded.classification,
          available_components_count = excluded.available_components_count,
          status = excluded.status,
          drivers = excluded.drivers,
          source_periods = excluded.source_periods,
          refreshed_at = now()
        """,
        [
            (row[0], row[1], row[2], row[3], row[4], row[5], json.dumps(row[6], ensure_ascii=False), json.dumps({"period": period.isoformat()}))
            for row in rows
        ],
    )
    return len(rows)


def upsert_opportunities(cur: Any) -> int:
    cur.execute(
        """
        insert into public.agg_market_opportunities(
          periodo_inicio, polo, uf, opportunities, high_relevance, total_value,
          avg_relevance_score, product_matches, refreshed_at
        )
        select
          date_trunc('month', data_publicacao)::date,
          '',
          coalesce(uf, 'NAO INFORMADO'),
          count(*)::int,
          count(*) filter (where relevance_score >= 5)::int,
          sum(valor_estimado),
          avg(relevance_score),
          '{}'::jsonb,
          now()
        from public.fact_pncp_opportunities
        where data_publicacao is not null
        group by 1, 3
        on conflict (periodo_inicio, polo, uf)
        do update set
          opportunities = excluded.opportunities,
          high_relevance = excluded.high_relevance,
          total_value = excluded.total_value,
          avg_relevance_score = excluded.avg_relevance_score,
          product_matches = excluded.product_matches,
          refreshed_at = now()
        """
    )
    return cur.rowcount if cur.rowcount is not None else 0


def upsert_cockpit(cur: Any) -> int:
    cur.execute("delete from public.agg_market_cockpit")
    cur.execute(
        """
        insert into public.agg_market_cockpit(
          periodo_inicio, signal_key, family, title, classification, score,
          available_components_count, drivers, target_tab, source_periods, refreshed_at
        )
        select
          periodo_inicio,
          'price_pressure_' || lower(regexp_replace(family, '[^a-zA-Z0-9]+', '_', 'g')),
          family,
          'Pressao de preco - ' || family,
          classification,
          score,
          available_components_count,
          jsonb_build_array(components),
          'market-prices',
          source_periods,
          now()
        from public.agg_market_price_pressure
        where periodo_inicio = (select max(periodo_inicio) from public.agg_market_price_pressure)
        union all
        select
          periodo_inicio,
          'demand_' || lower(regexp_replace(family, '[^a-zA-Z0-9]+', '_', 'g')),
          family,
          'Demanda - ' || family,
          classification,
          score,
          available_components_count,
          drivers,
          'industry',
          source_periods,
          now()
        from public.agg_market_demand_family
        where periodo_inicio = (select max(periodo_inicio) from public.agg_market_demand_family)
        """
    )
    return cur.rowcount if cur.rowcount is not None else 0


def refresh() -> dict[str, Any]:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            price_rows = upsert_price_pressure(cur)
            demand_rows = upsert_demand_family(cur)
            opportunity_rows = upsert_opportunities(cur)
            cockpit_rows = upsert_cockpit(cur)
            conn.commit()
    return {
        "status": "sucesso",
        "price_pressure_rows": price_rows,
        "demand_family_rows": demand_rows,
        "opportunity_rows": opportunity_rows,
        "cockpit_rows": cockpit_rows,
    }


if __name__ == "__main__":
    print(json.dumps(refresh(), ensure_ascii=False, indent=2))
