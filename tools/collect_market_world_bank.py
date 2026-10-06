from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.archive_storage import archive_records, require_drive_archive
from tools.apply_migrations import connect_market_database, load_env
from tools.market_indicator_quality import normalize_and_validate_indicators


SOURCE_KEY = "world_bank_wdi"
DEFAULT_BASE_URL = "https://api.worldbank.org/v2"
DEFAULT_COUNTRIES = "BRA;CHN;USA;WLD"
DEFAULT_INDICATORS = "NY.GDP.MKTP.KD.ZG;NV.IND.TOTL.KD.ZG;NV.IND.MANF.KD.ZG;NE.EXP.GNFS.KD.ZG;NE.IMP.GNFS.KD.ZG"


def start_run(cur: Any, metadata: dict[str, Any]) -> str:
    cur.execute(
        """
        insert into public.mercado_coletas(source_key, status, metadados)
        values (%s, 'processando', %s::jsonb)
        returning id
        """,
        (SOURCE_KEY, json.dumps(metadata, ensure_ascii=False)),
    )
    return str(cur.fetchone()[0])


def finish_run(cur: Any, run_id: str, *, status: str, found: int = 0, inserted: int = 0, error: str | None = None) -> None:
    cur.execute(
        """
        update public.mercado_coletas
        set status = %s,
            finalizado_em = now(),
            registros_encontrados = %s,
            registros_inseridos = %s,
            erro = %s
        where id = %s
        """,
        (status, found, inserted, error, run_id),
    )


def numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=20), reraise=True)
def fetch_indicator(base_url: str, countries: str, indicator: str, start_year: int, end_year: int) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/country/{countries}/indicator/{indicator}"
    params = {
        "format": "json",
        "per_page": 20000,
        "date": f"{start_year}:{end_year}",
    }
    with httpx.Client(timeout=90, follow_redirects=True, headers={"user-agent": "ABR-Intelligence/1.0"}) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        return []
    return payload[1]


def normalize_rows(payload_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in payload_rows:
        country = row.get("country") if isinstance(row.get("country"), dict) else {}
        indicator = row.get("indicator") if isinstance(row.get("indicator"), dict) else {}
        year = str(row.get("date") or "")
        if not year.isdigit():
            continue
        rows.append(
            {
                "country_code": str(row.get("countryiso3code") or country.get("id") or ""),
                "country_name": country.get("value"),
                "indicator_code": indicator.get("id"),
                "indicator_name": indicator.get("value"),
                "ano": int(year),
                "valor": numeric_value(row.get("value")),
                "unit": row.get("unit"),
                "obs_status": row.get("obs_status"),
                "payload": row,
            }
        )
    return rows


def indicator_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if row["valor"] is None:
            continue
        periodo = f"{row['ano']}-01-01"
        output.append(
            {
                "source_key": SOURCE_KEY,
                "indicador_key": f"world_bank_{row['indicator_code']}",
                "indicador_nome": row["indicator_name"],
                "periodo_inicio": periodo,
                "periodo_label": str(row["ano"]),
                "geografia": row["country_code"],
                "unidade": row.get("unit") or "%",
                "valor": row["valor"],
                "dimensoes": {
                    "country_code": row["country_code"],
                    "country_name": row["country_name"],
                    "indicator_code": row["indicator_code"],
                },
                "payload_original": row["payload"],
            }
        )
    return output


def collect_world_bank(*, dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    base_url = env.get("WORLD_BANK_API_BASE_URL") or DEFAULT_BASE_URL
    countries = env.get("WORLD_BANK_COUNTRIES") or DEFAULT_COUNTRIES
    indicators = [item.strip() for item in (env.get("WORLD_BANK_INDICATORS") or DEFAULT_INDICATORS).split(";") if item.strip()]
    start_year = int(env.get("WORLD_BANK_START_YEAR") or "2000")
    end_year = date.today().year

    rows: list[dict[str, Any]] = []
    for indicator in indicators:
        rows.extend(normalize_rows(fetch_indicator(base_url, countries, indicator, start_year, end_year)))

    indicators_to_insert = indicator_rows(rows)
    if dry_run:
        return {
            "source_key": SOURCE_KEY,
            "status": "dry_run",
            "rows_found": len(rows),
            "indicators_found": len(indicators_to_insert),
            "sample": rows[:5],
        }

    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(cur, {"base_url": base_url, "countries": countries, "indicators": indicators, "start_year": start_year, "end_year": end_year})
            try:
                archive = archive_records(
                    source_system="mercado_api",
                    entity=SOURCE_KEY,
                    sync_id=f"world_bank_{date.today():%Y%m%d}",
                    rows=rows,
                    metadata={"source_key": SOURCE_KEY, "base_url": base_url, "countries": countries, "indicators": indicators},
                    env=env,
                )
                require_drive_archive(archive, env=env)
                cur.execute("delete from public.raw_world_bank_indicator")
                cur.execute("delete from public.fact_world_bank_macro")
                cur.execute("delete from public.mercado_indicadores where source_key = %s", (SOURCE_KEY,))
                cur.executemany(
                    """
                    insert into public.raw_world_bank_indicator(
                      country_code, country_name, indicator_code, indicator_name, ano,
                      valor, unit, obs_status, payload, coletado_em
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    on conflict (country_code, indicator_code, ano)
                    do update set
                      country_name = excluded.country_name,
                      indicator_name = excluded.indicator_name,
                      valor = excluded.valor,
                      unit = excluded.unit,
                      obs_status = excluded.obs_status,
                      payload = excluded.payload,
                      coletado_em = now()
                    """,
                    [
                        (
                            row["country_code"],
                            row["country_name"],
                            row["indicator_code"],
                            row["indicator_name"],
                            row["ano"],
                            row["valor"],
                            row["unit"],
                            row["obs_status"],
                            json.dumps(row["payload"], ensure_ascii=False),
                        )
                        for row in rows
                    ],
                )
                cur.executemany(
                    """
                    insert into public.fact_world_bank_macro(
                      periodo_inicio, country_code, country_name, indicator_code,
                      indicator_name, valor, unidade, coletado_em
                    )
                    values (%s::date, %s, %s, %s, %s, %s, %s, now())
                    on conflict (periodo_inicio, country_code, indicator_code)
                    do update set
                      country_name = excluded.country_name,
                      indicator_name = excluded.indicator_name,
                      valor = excluded.valor,
                      unidade = excluded.unidade,
                      coletado_em = now()
                    """,
                    [
                        (
                            f"{row['ano']}-01-01",
                            row["country_code"],
                            row["country_name"],
                            row["indicator_code"],
                            row["indicator_name"],
                            row["valor"],
                            row["unit"] or "%",
                        )
                        for row in rows
                    ],
                )
                indicators_to_insert = normalize_and_validate_indicators(cur, indicators_to_insert)
                if indicators_to_insert:
                    cur.executemany(
                        """
                        insert into public.mercado_indicadores(
                          source_key, indicador_key, indicador_nome, periodo_inicio,
                          periodo_label, geografia, unidade, valor, dimensoes,
                          payload_original, coletado_em
                        )
                        values (%s, %s, %s, %s::date, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
                        """,
                        [
                            (
                                row["source_key"],
                                row["indicador_key"],
                                row["indicador_nome"],
                                row["periodo_inicio"],
                                row["periodo_label"],
                                row["geografia"],
                                row["unidade"],
                                row["valor"],
                                json.dumps(row["dimensoes"], ensure_ascii=False),
                                json.dumps(row["payload_original"], ensure_ascii=False),
                            )
                            for row in indicators_to_insert
                        ],
                    )
                finish_run(cur, run_id, status="sucesso", found=len(rows), inserted=len(indicators_to_insert))
                conn.commit()
                return {
                    "source_key": SOURCE_KEY,
                    "status": "sucesso",
                    "rows_found": len(rows),
                    "indicators_inserted": len(indicators_to_insert),
                    "archive_files": len(archive.get("files", [])),
                }
            except Exception as exc:
                finish_run(cur, run_id, status="erro", found=len(rows), inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta indicadores macro World Bank WDI.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = collect_world_bank(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
