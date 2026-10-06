from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.archive_storage import archive_records, require_drive_archive
from tools.apply_migrations import connect_market_database, load_env
from tools.market_indicator_quality import normalize_and_validate_indicators


DEFAULT_TIMEOUT = 60
DEFAULT_USER_AGENT = "ABR-Intelligence/1.0"


def parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    return date.fromisoformat(value)


def numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "...", "X"}:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def sidra_period_start(period_code: str | None) -> str | None:
    if not period_code:
        return None
    digits = "".join(char for char in str(period_code) if char.isdigit())
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}-01"
    if len(digits) == 4:
        return f"{digits}-01-01"
    return None


def re_match_period_code(value: str) -> bool:
    return bool(re.fullmatch(r"(19|20)\d{2}(0[1-9]|1[0-2])", value))


def start_run(cur: Any, source_key: str, metadata: dict[str, Any]) -> str:
    cur.execute(
        """
        insert into public.mercado_coletas(source_key, status, metadados)
        values (%s, 'processando', %s::jsonb)
        returning id
        """,
        (source_key, json.dumps(metadata, ensure_ascii=False)),
    )
    return str(cur.fetchone()[0])


def finish_run(
    cur: Any,
    run_id: str,
    *,
    status: str,
    found: int,
    inserted: int,
    error: str | None = None,
) -> None:
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


def insert_market_indicators(cur: Any, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    rows = normalize_and_validate_indicators(cur, rows)
    if not rows:
        return 0
    cur.executemany(
        """
        insert into public.mercado_indicadores(
          source_key, indicador_key, indicador_nome, periodo_inicio, periodo_fim,
          periodo_label, geografia, unidade, valor, valor_texto, dimensoes,
          payload_original, coletado_em
        )
        values (%s, %s, %s, %s::date, %s::date, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
        """,
        [
            (
                row["source_key"],
                row["indicador_key"],
                row["indicador_nome"],
                row.get("periodo_inicio"),
                row.get("periodo_fim"),
                row.get("periodo_label"),
                row.get("geografia", "BR"),
                row.get("unidade"),
                row.get("valor"),
                row.get("valor_texto"),
                json.dumps(row.get("dimensoes", {}), ensure_ascii=False),
                json.dumps(row.get("payload_original", {}), ensure_ascii=False),
            )
            for row in rows
        ],
    )
    return len(rows)


def collect_bcb_ptax(env: dict[str, str], client: httpx.Client, date_from: date, date_to: date, dry_run: bool) -> dict[str, Any]:
    source_key = "bcb_dolar_ptax"
    base_url = (env.get("BCB_DOLAR_API_BASE_URL") or "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata").rstrip("/")
    url = (
        f"{base_url}/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        f"?@dataInicial='{date_from:%m-%d-%Y}'&@dataFinalCotacao='{date_to:%m-%d-%Y}'&$format=json"
    )
    response = client.get(url)
    response.raise_for_status()
    rows = response.json().get("value", [])
    sync_id = f"bcb_ptax_{date_from:%Y%m%d}_{date_to:%Y%m%d}"
    indicators: list[dict[str, Any]] = []
    for row in rows:
        quote_at = datetime.fromisoformat(str(row["dataHoraCotacao"]).replace("Z", "+00:00"))
        period = quote_at.date().isoformat()
        for kind, name in (("cotacaoCompra", "Dolar PTAX compra"), ("cotacaoVenda", "Dolar PTAX venda")):
            indicators.append(
                {
                    "source_key": source_key,
                    "indicador_key": f"bcb_ptax_{kind}",
                    "indicador_nome": name,
                    "periodo_inicio": period,
                    "periodo_label": period,
                    "geografia": "BR",
                    "unidade": "BRL/USD",
                    "valor": numeric_value(row.get(kind)),
                    "dimensoes": {"tipo_boletim": row.get("tipoBoletim")},
                    "payload_original": row,
                }
            )
    if dry_run:
        return {"source_key": source_key, "records_found": len(rows), "indicators_found": len(indicators), "sample": rows[:3]}
    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(cur, source_key, {"url": url, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()})
            try:
                archive = archive_records(
                    source_system="mercado_api",
                    entity=source_key,
                    sync_id=sync_id,
                    rows=rows,
                    metadata={"source_key": source_key, "url": url},
                    env=env,
                )
                require_drive_archive(archive, env=env)
                cur.executemany(
                    """
                    insert into public.raw_bcb_ptax(
                      data_cotacao, data_hora_cotacao, tipo_boletim, cotacao_compra,
                      cotacao_venda, payload, coletado_em
                    )
                    values (%s::date, %s::timestamptz, %s, %s, %s, %s::jsonb, now())
                    on conflict (data_hora_cotacao, coalesce(tipo_boletim, ''))
                    do update set
                      cotacao_compra = excluded.cotacao_compra,
                      cotacao_venda = excluded.cotacao_venda,
                      payload = excluded.payload,
                      coletado_em = now()
                    """,
                    [
                        (
                            datetime.fromisoformat(str(row["dataHoraCotacao"]).replace("Z", "+00:00")).date().isoformat(),
                            row["dataHoraCotacao"],
                            row.get("tipoBoletim"),
                            numeric_value(row.get("cotacaoCompra")),
                            numeric_value(row.get("cotacaoVenda")),
                            json.dumps(row, ensure_ascii=False),
                        )
                        for row in rows
                    ],
                )
                cur.execute(
                    """
                    delete from public.mercado_indicadores
                    where source_key = %s
                      and indicador_key in ('bcb_ptax_cotacaoCompra', 'bcb_ptax_cotacaoVenda')
                      and periodo_inicio between %s::date and %s::date
                    """,
                    (source_key, date_from.isoformat(), date_to.isoformat()),
                )
                inserted = insert_market_indicators(cur, indicators)
                finish_run(cur, run_id, status="sucesso", found=len(rows), inserted=inserted)
                conn.commit()
                return {
                    "source_key": source_key,
                    "status": "sucesso",
                    "records_found": len(rows),
                    "indicators_inserted": inserted,
                    "archive_files": len(archive.get("files", [])),
                }
            except Exception as exc:
                finish_run(cur, run_id, status="erro", found=len(rows), inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise


def sidra_url(env: dict[str, str], table_id: str, path: str) -> str:
    base_url = (env.get("IBGE_SIDRA_VALUES_BASE_URL") or "https://apisidra.ibge.gov.br/values").rstrip("/")
    return f"{base_url}/t/{table_id}{path if path.startswith('/') else '/' + path}"


def sidra_extract_rows(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not payload:
        return []
    first = payload[0]
    if all(isinstance(value, str) for value in first.values()):
        return payload[1:]
    return payload


def sidra_dimension(row: dict[str, Any], prefix: str) -> tuple[str | None, str | None]:
    return row.get(f"{prefix}C"), row.get(f"{prefix}N")


def normalize_sidra_row(source_key: str, table_id: str, row: dict[str, Any]) -> dict[str, Any]:
    period_code: str | None = None
    period_label: str | None = None
    classification_code: str | None = None
    classification_name: str | None = None
    category_code: str | None = None
    category_name: str | None = None
    for index in range(1, 10):
        code, label = sidra_dimension(row, f"D{index}")
        code_text = str(code or "")
        if re_match_period_code(code_text):
            period_code, period_label = code_text, label
            continue
        if index in {1, 2}:
            continue
        if code is not None and classification_code is None:
            classification_code, classification_name = str(code), label
        elif code is not None and category_code is None:
            category_code, category_name = str(code), label
    geography_code, geography_name = sidra_dimension(row, "D1")
    variable_id = row.get("MC") or row.get("MNC") or row.get("MN")
    value = numeric_value(row.get("V"))
    return {
        "source_key": source_key,
        "table_id": table_id,
        "variable_id": str(variable_id) if variable_id is not None else None,
        "period_code": str(period_code) if period_code is not None else None,
        "period_label": str(period_label) if period_label is not None else None,
        "geography_code": str(geography_code) if geography_code is not None else None,
        "geography_name": str(geography_name) if geography_name is not None else None,
        "classification_code": str(classification_code) if classification_code is not None else None,
        "classification_name": str(classification_name) if classification_name is not None else None,
        "category_code": str(category_code) if category_code is not None else None,
        "category_name": str(category_name) if category_name is not None else None,
        "value": value,
        "value_text": str(row.get("V")) if row.get("V") is not None else None,
        "payload": row,
    }


def collect_ibge_sidra_source(
    env: dict[str, str],
    client: httpx.Client,
    *,
    source_key: str,
    table_env: str,
    default_table: str,
    path_env: str,
    default_path: str,
    dry_run: bool,
) -> dict[str, Any]:
    table_id = env.get(table_env) or default_table
    path = env.get(path_env) or default_path
    url = sidra_url(env, table_id, path)
    response = client.get(url)
    response.raise_for_status()
    payload = response.json()
    raw_rows = sidra_extract_rows(payload)
    rows = [normalize_sidra_row(source_key, table_id, row) for row in raw_rows]
    sync_id = f"{source_key}_{date.today():%Y%m%d}"
    indicator_key = "ibge_pim_producao_fisica" if source_key == "ibge_pim_sidra" else "ibge_construcao_indice"
    indicator_name = "IBGE PIM producao fisica" if source_key == "ibge_pim_sidra" else "IBGE construcao indice"
    indicators = [
        {
            "source_key": source_key,
            "indicador_key": indicator_key,
            "indicador_nome": indicator_name,
            "periodo_inicio": sidra_period_start(row["period_code"]),
            "periodo_label": row["period_label"] or row["period_code"],
            "geografia": row["geography_name"] or "BR",
            "unidade": "indice",
            "valor": row["value"],
            "valor_texto": row["value_text"],
            "dimensoes": {
                "table_id": table_id,
                "variable_id": row["variable_id"],
                "classification_code": row["classification_code"],
                "classification_name": row["classification_name"],
                "category_code": row["category_code"],
                "category_name": row["category_name"],
            },
            "payload_original": row["payload"],
        }
        for row in rows
        if row["value"] is not None and sidra_period_start(row["period_code"])
    ]
    if dry_run:
        return {"source_key": source_key, "records_found": len(rows), "indicators_found": len(indicators), "sample": rows[:3]}
    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(cur, source_key, {"url": url, "table_id": table_id, "path": path})
            try:
                archive = archive_records(
                    source_system="mercado_api",
                    entity=source_key,
                    sync_id=sync_id,
                    rows=raw_rows,
                    metadata={"source_key": source_key, "url": url, "table_id": table_id, "path": path},
                    env=env,
                )
                require_drive_archive(archive, env=env)
                cur.executemany(
                    """
                    insert into public.raw_ibge_sidra(
                      source_key, table_id, variable_id, period_code, period_label,
                      geography_code, geography_name, classification_code, classification_name,
                      category_code, category_name, value, value_text, payload, coletado_em
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    on conflict (
                      source_key, table_id, coalesce(variable_id, ''), coalesce(period_code, ''),
                      coalesce(geography_code, ''), coalesce(classification_code, ''), coalesce(category_code, '')
                    )
                    do update set
                      period_label = excluded.period_label,
                      geography_name = excluded.geography_name,
                      classification_name = excluded.classification_name,
                      category_name = excluded.category_name,
                      value = excluded.value,
                      value_text = excluded.value_text,
                      payload = excluded.payload,
                      coletado_em = now()
                    """,
                    [
                        (
                            row["source_key"],
                            row["table_id"],
                            row["variable_id"],
                            row["period_code"],
                            row["period_label"],
                            row["geography_code"],
                            row["geography_name"],
                            row["classification_code"],
                            row["classification_name"],
                            row["category_code"],
                            row["category_name"],
                            row["value"],
                            row["value_text"],
                            json.dumps(row["payload"], ensure_ascii=False),
                        )
                        for row in rows
                    ],
                )
                periods = [sidra_period_start(row["period_code"]) for row in rows if sidra_period_start(row["period_code"])]
                if periods:
                    cur.execute(
                        """
                        delete from public.mercado_indicadores
                        where source_key = %s
                          and indicador_key = %s
                          and periodo_inicio between %s::date and %s::date
                        """,
                        (source_key, indicator_key, min(periods), max(periods)),
                    )
                inserted = insert_market_indicators(cur, indicators)
                finish_run(cur, run_id, status="sucesso", found=len(rows), inserted=inserted)
                conn.commit()
                return {
                    "source_key": source_key,
                    "status": "sucesso",
                    "records_found": len(rows),
                    "indicators_inserted": inserted,
                    "archive_files": len(archive.get("files", [])),
                }
            except Exception as exc:
                finish_run(cur, run_id, status="erro", found=len(rows), inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise


def collect_sources(source_keys: list[str], date_from: date, date_to: date, dry_run: bool) -> dict[str, Any]:
    env = load_env()
    timeout = int(env.get("EXTERNAL_DATA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
    headers = {"user-agent": env.get("EXTERNAL_DATA_USER_AGENT") or DEFAULT_USER_AGENT}
    result: dict[str, Any] = {"sources": []}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        if "bcb_dolar_ptax" in source_keys:
            result["sources"].append(collect_bcb_ptax(env, client, date_from, date_to, dry_run=dry_run))
        if "ibge_pim_sidra" in source_keys:
            result["sources"].append(
                collect_ibge_sidra_source(
                    env,
                    client,
                    source_key="ibge_pim_sidra",
                    table_env="IBGE_PIM_TABLE_ID",
                    default_table="8888",
                    path_env="IBGE_PIM_DEFAULT_PATH",
                    default_path="/n1/all/v/12606/p/last%2036/c544/all",
                    dry_run=dry_run,
                )
            )
        if "ibge_construcao_sidra" in source_keys:
            result["sources"].append(
                collect_ibge_sidra_source(
                    env,
                    client,
                    source_key="ibge_construcao_sidra",
                    table_env="IBGE_CONSTRUCTION_TABLE_ID",
                    default_table="8886",
                    path_env="IBGE_CONSTRUCTION_DEFAULT_PATH",
                    default_path="/n1/all/v/12606/p/last%2036",
                    dry_run=dry_run,
                )
            )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta fontes API de mercado.")
    parser.add_argument(
        "--source",
        action="append",
        choices=["bcb_dolar_ptax", "ibge_pim_sidra", "ibge_construcao_sidra", "all"],
        default=None,
    )
    parser.add_argument("--date-from", default=None)
    parser.add_argument("--date-to", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested = args.source or ["all"]
    source_keys = (
        ["bcb_dolar_ptax", "ibge_pim_sidra", "ibge_construcao_sidra"]
        if "all" in requested
        else requested
    )
    today = date.today()
    date_from = parse_date(args.date_from, today - timedelta(days=45))
    date_to = parse_date(args.date_to, today)
    result = collect_sources(source_keys, date_from, date_to, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
