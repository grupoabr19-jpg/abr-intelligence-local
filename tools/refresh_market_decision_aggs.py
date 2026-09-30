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


def latest_series_period(series: dict[date, Decimal], cutoff: date) -> date | None:
    candidates = [period for period in series if period <= cutoff]
    return max(candidates) if candidates else None


def previous_year_period(period: date) -> date:
    return date(period.year - 1, period.month, 1)


def latest_series_change(series: dict[date, Decimal], cutoff: date) -> tuple[Decimal | None, date | None, Decimal | None]:
    current_period = latest_series_period(series, cutoff)
    if not current_period:
        return None, None, None
    change = pct_change(series.get(current_period), series.get(previous_year_period(current_period)))
    return change, current_period, series.get(current_period)


def compact_signal(signals: list[int | None]) -> int | None:
    valid = [item for item in signals if item is not None]
    if not valid:
        return None
    score = sum(valid)
    if score > 0:
        return 1
    if score < 0:
        return -1
    return 0


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


def latest_indicator_value(cur: Any, source_key: str, indicator_key: str, period: date) -> tuple[Decimal | None, date | None, str | None]:
    cur.execute(
        """
        select valor, periodo_inicio, periodo_label
        from public.mercado_indicadores
        where source_key = %s
          and indicador_key = %s
          and periodo_inicio <= %s
          and valor is not null
        order by periodo_inicio desc nulls last, coletado_em desc
        limit 1
        """,
        (source_key, indicator_key, period),
    )
    row = cur.fetchone()
    if not row:
        return None, None, None
    return as_decimal(row[0]), row[1], row[2]


def latest_drivers_from_patterns(cur: Any, source_key: str, patterns: tuple[str, ...], period: date, limit: int = 12) -> list[Driver]:
    clauses = " or ".join(["indicador_key ilike %s or indicador_nome ilike %s" for _ in patterns])
    params: list[Any] = []
    for pattern in patterns:
        params.extend([f"%{pattern}%", f"%{pattern}%"])
    cur.execute(
        f"""
        select indicador_nome, valor, periodo_label, source_key
        from (
          select
            indicador_key,
            indicador_nome,
            valor,
            periodo_label,
            source_key,
            row_number() over (
              partition by indicador_key
              order by periodo_inicio desc nulls last, coletado_em desc
            ) as ordem
          from public.mercado_indicadores
          where source_key = %s
            and periodo_inicio <= %s
            and valor is not null
            and ({clauses})
        ) ranked
        where ordem = 1
        order by indicador_nome
        limit %s
        """,
        [source_key, period, *params, limit],
    )
    rows = cur.fetchall()
    return [
        Driver(row[0], as_decimal(row[1]), cni_signal(as_decimal(row[1])), row[3], row[2])
        for row in rows
    ]


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
    internal_sales = fetch_monthly_indicator(cur, "aco_brasil_estatistica_mensal", "aco_brasil_vendas_internas_total")
    cur.execute("select max(periodo_inicio) from public.mercado_indicadores")
    latest = cur.fetchone()[0]
    if not latest:
        return 0
    period = month_start(latest)

    rows = []
    for family in FAMILIES:
        fx_change, fx_period, fx_value = latest_series_change(ptax, period)
        fx_signal = signal_from_pct(fx_change)

        consumption_change, consumption_period, consumption_value = latest_series_change(consumption, period)
        consumption_signal = signal_from_pct(consumption_change, Decimal("3"))
        sales_change, sales_period, sales_value = latest_series_change(internal_sales, period)
        sales_signal = signal_from_pct(sales_change, Decimal("3"))
        demand_signal = compact_signal([consumption_signal, sales_signal])

        family_keys = [key for key, value in COMEX_TO_DECISION_FAMILY.items() if value == family]
        cur.execute(
            """
            select max(periodo_inicio)
            from public.fact_steel_import_monthly
            where periodo_inicio <= %s
              and familia_abr = any(%s)
            """,
            (period, family_keys),
        )
        import_period = cur.fetchone()[0]

        cur.execute(
            """
            with current_3m as (
              select coalesce(sum(toneladas), 0) tons, coalesce(sum(vl_fob_usd), 0) fob
              from public.fact_steel_import_monthly
              where %s::date is not null
                and periodo_inicio between (%s::date - interval '2 months') and %s::date
                and familia_abr = any(%s)
            ),
            previous_3m as (
              select coalesce(sum(toneladas), 0) tons, coalesce(sum(vl_fob_usd), 0) fob
              from public.fact_steel_import_monthly
              where %s::date is not null
                and periodo_inicio between (%s::date - interval '1 year' - interval '2 months') and (%s::date - interval '1 year')
                and familia_abr = any(%s)
            )
            select current_3m.tons, current_3m.fob, previous_3m.tons, previous_3m.fob
            from current_3m, previous_3m
            """,
            (
                import_period,
                import_period,
                import_period,
                family_keys,
                import_period,
                import_period,
                import_period,
                family_keys,
            ),
        )
        tons_now, fob_now, tons_prev, fob_prev = [as_decimal(item) for item in cur.fetchone()]
        import_change = pct_change(tons_now, tons_prev)
        import_signal = inverse_supply_signal(import_change)
        fob_now_t = fob_now / tons_now if tons_now and tons_now != 0 else None
        fob_prev_t = fob_prev / tons_prev if tons_prev and tons_prev != 0 else None
        fob_signal = signal_from_pct(pct_change(fob_now_t, fob_prev_t))

        inda_stock_yoy, inda_period, _ = latest_indicator_value(cur, "inda_estatisticas", "inda_estoque_variacao_ano_pct", period)
        inda_stock_mom, inda_mom_period, _ = latest_indicator_value(cur, "inda_estatisticas", "inda_estoque_variacao_mes_pct", period)
        inda_signal = compact_signal([
            inverse_supply_signal(inda_stock_yoy, Decimal("5")),
            inverse_supply_signal(inda_stock_mom, Decimal("3")),
        ])

        signals = [fx_signal, fob_signal, import_signal, inda_signal, consumption_signal, sales_signal]
        available = len([item for item in signals if item is not None])
        score = sum(item for item in signals if item is not None) if available else None
        classification, status = classify_score(score, available, "PRESSAO DE ALTA", "PRESSAO DE BAIXA")
        components = {
            "fx_change_pct": str(fx_change) if fx_change is not None else None,
            "fx_value": str(fx_value) if fx_value is not None else None,
            "fob_usd_t": str(fob_now_t) if fob_now_t is not None else None,
            "import_3m_yoy_pct": str(import_change) if import_change is not None else None,
            "inda_stock_yoy_pct": str(inda_stock_yoy) if inda_stock_yoy is not None else None,
            "inda_stock_mom_pct": str(inda_stock_mom) if inda_stock_mom is not None else None,
            "inda_stock_signal": inda_signal,
            "aco_consumption_yoy_pct": str(consumption_change) if consumption_change is not None else None,
            "aco_internal_sales_yoy_pct": str(sales_change) if sales_change is not None else None,
        }
        source_periods = {
            "analysis_period": period.isoformat(),
            "ptax": fx_period.isoformat() if fx_period else None,
            "comex": import_period.isoformat() if import_period else None,
            "inda_stock_yoy": inda_period.isoformat() if inda_period else None,
            "inda_stock_mom": inda_mom_period.isoformat() if inda_mom_period else None,
            "aco_consumption": consumption_period.isoformat() if consumption_period else None,
            "aco_internal_sales": sales_period.isoformat() if sales_period else None,
        }
        rows.append((period, family, fx_signal, fob_signal, import_signal, inda_signal, demand_signal, score, classification, available, status, components, source_periods))

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
                *row[:-2],
                json.dumps(row[-2], ensure_ascii=False),
                json.dumps(row[-1], ensure_ascii=False),
            )
            for row in rows
        ],
    )
    return len(rows)


def demand_drivers(cur: Any, family: str, period: date) -> list[Driver]:
    drivers: list[Driver] = []
    industry_drivers = latest_drivers_from_patterns(
        cur,
        "cni_sondagem_industrial",
        ("demanda", "compras", "producao", "capacidade", "empregados", "estoque"),
        period,
        limit=10,
    )
    construction_drivers = latest_drivers_from_patterns(
        cur,
        "cni_sondagem_construcao",
        ("atividade", "compras", "insumos", "empreendimentos", "empregados"),
        period,
        limit=10,
    )

    pim_change, pim_period, pim_value = latest_series_change(fetch_monthly_indicator(cur, "ibge_pim_sidra", "ibge_pim_producao_fisica"), period)
    if pim_period:
        drivers.append(Driver("IBGE PIM producao fisica YoY", pim_value, signal_from_pct(pim_change, Decimal("2")), "ibge_pim_sidra", pim_period.isoformat()))
    construction_change, construction_period, construction_value = latest_series_change(fetch_monthly_indicator(cur, "ibge_construcao_sidra", "ibge_construcao_indice"), period)
    if construction_period:
        drivers.append(Driver("IBGE construcao indice YoY", construction_value, signal_from_pct(construction_change, Decimal("2")), "ibge_construcao_sidra", construction_period.isoformat()))

    consumption_change, consumption_period, consumption_value = latest_series_change(
        fetch_monthly_indicator(cur, "aco_brasil_estatistica_mensal", "aco_brasil_consumo_aparente_total"),
        period,
    )
    if consumption_period:
        drivers.append(Driver("Aco Brasil consumo aparente YoY", consumption_value, signal_from_pct(consumption_change, Decimal("3")), "aco_brasil_estatistica_mensal", consumption_period.isoformat()))
    sales_change, sales_period, sales_value = latest_series_change(
        fetch_monthly_indicator(cur, "aco_brasil_estatistica_mensal", "aco_brasil_vendas_internas_total"),
        period,
    )
    if sales_period:
        drivers.append(Driver("Aco Brasil vendas internas YoY", sales_value, signal_from_pct(sales_change, Decimal("3")), "aco_brasil_estatistica_mensal", sales_period.isoformat()))

    for indicator_key, label, threshold in (
        ("inda_vendas_variacao_ano_pct", "INDA vendas variacao anual", Decimal("3")),
        ("inda_compras_variacao_ano_pct", "INDA compras variacao anual", Decimal("3")),
    ):
        value, driver_period, period_label = latest_indicator_value(cur, "inda_estatisticas", indicator_key, period)
        if driver_period:
            drivers.append(Driver(label, value, signal_from_pct(value, threshold), "inda_estatisticas", period_label or driver_period.isoformat()))

    if family in {"CHAPAS", "TUBOS / METALONS"}:
        return [*industry_drivers, *drivers]
    if family in {"PERFIS", "TELHAS"}:
        return [*construction_drivers, *drivers]
    return [*industry_drivers, *construction_drivers, *drivers]


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
        source_periods: dict[str, list[str]] = defaultdict(list)
        for item in drivers:
            if item.period and item.period not in source_periods[item.source]:
                source_periods[item.source].append(item.period)
        rows.append((period, family, score, classification, available, status, payload, dict(source_periods)))

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
            (row[0], row[1], row[2], row[3], row[4], row[5], json.dumps(row[6], ensure_ascii=False), json.dumps(row[7], ensure_ascii=False))
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
    base_rows = cur.rowcount if cur.rowcount is not None else 0
    cur.execute(
        """
        insert into public.agg_market_cockpit(
          periodo_inicio, signal_key, family, title, classification, score,
          available_components_count, drivers, target_tab, source_periods, refreshed_at
        )
        with latest_solar as (
          select max(periodo_inicio) as periodo_inicio
          from public.fact_solar_monthly
        ),
        solar_current as (
          select
            latest_solar.periodo_inicio,
            coalesce(sum(fsm.new_mw), 0) as current_12m_mw,
            coalesce(sum(fsm.novas_instalacoes), 0) as current_12m_installations
          from latest_solar
          join public.fact_solar_monthly fsm
            on fsm.periodo_inicio between (latest_solar.periodo_inicio - interval '11 months') and latest_solar.periodo_inicio
          group by latest_solar.periodo_inicio
        ),
        solar_previous as (
          select
            latest_solar.periodo_inicio,
            coalesce(sum(fsm.new_mw), 0) as previous_12m_mw,
            coalesce(sum(fsm.novas_instalacoes), 0) as previous_12m_installations
          from latest_solar
          join public.fact_solar_monthly fsm
            on fsm.periodo_inicio between (latest_solar.periodo_inicio - interval '23 months') and (latest_solar.periodo_inicio - interval '12 months')
          group by latest_solar.periodo_inicio
        )
        select
          solar_current.periodo_inicio,
          'solar_momentum',
          '',
          'Solar GD - expansao 12M',
          case
            when nullif(solar_previous.previous_12m_mw, 0) is null then 'INSUFFICIENT_DATA'
            when solar_current.current_12m_mw >= solar_previous.previous_12m_mw * 1.15 then 'EXPANSAO'
            when solar_current.current_12m_mw <= solar_previous.previous_12m_mw * 0.85 then 'DESACELERANDO'
            else 'ESTAVEL'
          end,
          case
            when nullif(solar_previous.previous_12m_mw, 0) is null then null
            when solar_current.current_12m_mw >= solar_previous.previous_12m_mw * 1.15 then 1
            when solar_current.current_12m_mw <= solar_previous.previous_12m_mw * 0.85 then -1
            else 0
          end,
          case when nullif(solar_previous.previous_12m_mw, 0) is null then 1 else 3 end,
          jsonb_build_array(
            jsonb_build_object(
              'name', 'ANEEL solar GD 12M',
              'source', 'aneel_dados_abertos',
              'current_12m_mw', solar_current.current_12m_mw,
              'previous_12m_mw', solar_previous.previous_12m_mw,
              'current_12m_installations', solar_current.current_12m_installations,
              'previous_12m_installations', solar_previous.previous_12m_installations
            )
          ),
          'solar',
          jsonb_build_object('aneel_dados_abertos', solar_current.periodo_inicio::text),
          now()
        from solar_current
        left join solar_previous using (periodo_inicio)
        """
    )
    solar_rows = cur.rowcount if cur.rowcount is not None else 0
    cur.execute(
        """
        insert into public.agg_market_cockpit(
          periodo_inicio, signal_key, family, title, classification, score,
          available_components_count, drivers, target_tab, source_periods, refreshed_at
        )
        with latest_macro as (
          select max(periodo_inicio) as periodo_inicio
          from public.fact_world_bank_macro
          where valor is not null
        ),
        macro as (
          select
            fwm.periodo_inicio,
            fwm.country_code,
            fwm.indicator_code,
            fwm.indicator_name,
            fwm.valor
          from public.fact_world_bank_macro fwm
          join latest_macro lm on lm.periodo_inicio = fwm.periodo_inicio
          where fwm.valor is not null
            and fwm.country_code in ('BRA', 'CHN', 'WLD')
            and fwm.indicator_code in ('NY.GDP.MKTP.KD.ZG', 'NV.IND.TOTL.KD.ZG', 'NV.IND.MANF.KD.ZG')
        ),
        scored as (
          select
            max(periodo_inicio) as periodo_inicio,
            count(*)::int as available_components_count,
            sum(
              case
                when valor >= 3 then 1
                when valor <= 0 then -1
                else 0
              end
            )::int as score,
            jsonb_agg(
              jsonb_build_object(
                'name', country_code || ' - ' || indicator_name,
                'source', 'world_bank_wdi',
                'indicator', indicator_code,
                'value', valor,
                'period', periodo_inicio
              )
              order by country_code, indicator_code
            ) as drivers,
            jsonb_object_agg(country_code || '_' || indicator_code, periodo_inicio::text) as source_periods
          from macro
        )
        select
          periodo_inicio,
          'macro_industrial_context',
          '',
          'Contexto macro industrial',
          case
            when available_components_count < 3 then 'INSUFFICIENT_DATA'
            when score >= 2 then 'FAVORAVEL'
            when score <= -2 then 'DESFAVORAVEL'
            else 'MISTO / NEUTRO'
          end,
          score,
          available_components_count,
          drivers,
          'market-overview',
          source_periods,
          now()
        from scored
        where periodo_inicio is not null
        """
    )
    macro_rows = cur.rowcount if cur.rowcount is not None else 0
    cur.execute(
        """
        insert into public.agg_market_cockpit(
          periodo_inicio, signal_key, family, title, classification, score,
          available_components_count, drivers, target_tab, source_periods, refreshed_at
        )
        with latest_obras as (
          select max(periodo_inicio) as periodo_inicio
          from public.fact_obrasgov_investments
        ),
        obras as (
          select
            foi.periodo_inicio,
            sum(foi.projetos)::int as projetos,
            sum(foi.investimento_previsto) as investimento_previsto,
            sum(foi.empregos_gerados) as empregos_gerados,
            count(distinct foi.uf)::int as ufs
          from public.fact_obrasgov_investments foi
          join latest_obras lo on lo.periodo_inicio = foi.periodo_inicio
          group by foi.periodo_inicio
        )
        select
          periodo_inicio,
          'public_works_pipeline',
          '',
          'ObrasGov - pipeline publico',
          case
            when projetos is null or projetos = 0 then 'INSUFFICIENT_DATA'
            when investimento_previsto >= 10000000000 then 'ALTA OPORTUNIDADE'
            when investimento_previsto >= 1000000000 then 'OPORTUNIDADE MODERADA'
            else 'BAIXA OPORTUNIDADE'
          end,
          case
            when projetos is null or projetos = 0 then null
            when investimento_previsto >= 10000000000 then 1
            when investimento_previsto >= 1000000000 then 0
            else -1
          end,
          case when projetos is null or projetos = 0 then 1 else 4 end,
          jsonb_build_array(
            jsonb_build_object(
              'name', 'ObrasGov projetos cadastrados',
              'source', 'obrasgov_projetos',
              'projects', projetos,
              'investment', investimento_previsto,
              'jobs', empregos_gerados,
              'ufs', ufs
            )
          ),
          'construction',
          jsonb_build_object('obrasgov_projetos', periodo_inicio::text),
          now()
        from obras
        where periodo_inicio is not null
        """
    )
    obras_rows = cur.rowcount if cur.rowcount is not None else 0
    return base_rows + solar_rows + macro_rows + obras_rows


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
