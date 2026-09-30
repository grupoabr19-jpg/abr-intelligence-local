from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.archive_storage import archive_records, require_drive_archive
from tools.apply_migrations import connect_database, load_env


SOURCE_KEY = "aneel_dados_abertos"
DATASET_ID = "relacao-de-empreendimentos-de-geracao-distribuida"
GENERAL_PARQUET_NAME = "empreendimento-geracao-distribuida.parquet"
DEFAULT_USER_AGENT = "ABR-Intelligence/1.0"

GENERAL_COLUMNS = [
    "DthAtualizaCadastralEmpreend",
    "NomMunicipio",
    "SigUF",
    "DscClasseConsumo",
    "SigTipoGeracao",
    "DscFonteGeracao",
    "MdaPotenciaInstaladaKW",
]

MIN_VALID_PERIOD = date(2000, 1, 1)


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


def numeric_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, float) and math.isnan(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def ckan_action_base(env: dict[str, str]) -> str:
    base_url = (env.get("ANEEL_API_BASE_URL") or "https://dadosabertos.aneel.gov.br").rstrip("/")
    if base_url.endswith("/api/3/action"):
        return base_url
    return f"{base_url}/api/3/action"


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=20), reraise=True)
def discover_general_parquet(env: dict[str, str]) -> dict[str, Any]:
    headers = {"user-agent": env.get("EXTERNAL_DATA_USER_AGENT") or DEFAULT_USER_AGENT}
    response = requests.get(
        f"{ckan_action_base(env)}/package_show",
        params={"id": DATASET_ID},
        headers=headers,
        timeout=60,
        allow_redirects=True,
    )
    response.raise_for_status()
    result = response.json()["result"]
    parquet_resources = [
        resource
        for resource in result.get("resources", [])
        if "parquet" in str(resource.get("format") or "").lower()
        or str(resource.get("url") or "").lower().endswith(".parquet")
    ]
    for resource in parquet_resources:
        url = str(resource.get("url") or "")
        name = str(resource.get("name") or "")
        if GENERAL_PARQUET_NAME in url.lower() or GENERAL_PARQUET_NAME in name.lower():
            return resource
    if parquet_resources:
        return parquet_resources[0]
    raise RuntimeError(f"Nenhum recurso Parquet encontrado no dataset {DATASET_ID}.")


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=20), reraise=True)
def download_file(url: str, destination: Path, env: dict[str, str]) -> int:
    headers = {"user-agent": env.get("EXTERNAL_DATA_USER_AGENT") or DEFAULT_USER_AGENT}
    total = 0
    with requests.get(url, stream=True, headers=headers, timeout=900, allow_redirects=True) as response:
        response.raise_for_status()
        with destination.open("wb") as file_obj:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    file_obj.write(chunk)
                    total += len(chunk)
    return total


def month_start(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    period = date(int(timestamp.year), int(timestamp.month), 1)
    max_valid = date(date.today().year + 1, 12, 1)
    if period < MIN_VALID_PERIOD or period > max_valid:
        return None
    return period.isoformat()


def clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def is_solar_frame(frame: pd.DataFrame) -> pd.Series:
    source = frame["DscFonteGeracao"].fillna("").astype(str).str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii").str.lower()
    generation_type = frame["SigTipoGeracao"].fillna("").astype(str).str.lower()
    return source.str.contains("radiacao solar|solar|fotovolta", regex=True) | generation_type.eq("ufv")


def aggregate_parquet(parquet_path: Path, *, max_row_groups: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parquet_file = pq.ParquetFile(parquet_path)
    available = set(parquet_file.schema_arrow.names)
    missing = [column for column in GENERAL_COLUMNS if column not in available]
    if missing:
        raise RuntimeError(f"Colunas ANEEL ausentes no Parquet: {', '.join(missing)}")

    aggregates: dict[tuple[str, str | None, str | None, str | None, str | None], dict[str, Any]] = {}
    row_groups = parquet_file.num_row_groups if max_row_groups is None else min(max_row_groups, parquet_file.num_row_groups)
    rows_read = 0
    solar_rows = 0

    for row_group in range(row_groups):
        table = parquet_file.read_row_group(row_group, columns=GENERAL_COLUMNS)
        frame = table.to_pandas()
        rows_read += len(frame)
        frame = frame[is_solar_frame(frame)].copy()
        solar_rows += len(frame)
        if frame.empty:
            continue
        frame["periodo_inicio"] = frame["DthAtualizaCadastralEmpreend"].map(month_start)
        frame = frame[frame["periodo_inicio"].notna()]
        frame["municipio"] = frame["NomMunicipio"].map(clean_text)
        frame["uf"] = frame["SigUF"].map(clean_text)
        frame["classe"] = frame["DscClasseConsumo"].map(clean_text)
        frame["fonte"] = frame["DscFonteGeracao"].map(clean_text)
        frame["potencia_kw"] = frame["MdaPotenciaInstaladaKW"].map(numeric_value)
        grouped = (
            frame.groupby(["periodo_inicio", "municipio", "uf", "classe", "fonte"], dropna=False)
            .agg(potencia_kw=("potencia_kw", "sum"), novas_instalacoes=("potencia_kw", "size"))
            .reset_index()
        )
        for row in grouped.to_dict("records"):
            key = (
                str(row["periodo_inicio"]),
                clean_text(row.get("municipio")),
                clean_text(row.get("uf")),
                clean_text(row.get("classe")),
                clean_text(row.get("fonte")),
            )
            item = aggregates.setdefault(
                key,
                {
                    "periodo_inicio": key[0],
                    "data_conexao": key[0],
                    "municipio": key[1],
                    "uf": key[2],
                    "classe": key[3],
                    "fonte": key[4],
                    "potencia_kw": 0.0,
                    "novas_instalacoes": 0,
                    "data_source": "DthAtualizaCadastralEmpreend",
                },
            )
            item["potencia_kw"] += numeric_value(row.get("potencia_kw"))
            item["novas_instalacoes"] += int(row.get("novas_instalacoes") or 0)

    aggregated_rows = list(aggregates.values())
    for row in aggregated_rows:
        row["new_mw"] = row["potencia_kw"] / 1000

    cumulative_by_group: dict[tuple[str | None, str | None, str | None, str | None], float] = defaultdict(float)
    for row in sorted(aggregated_rows, key=lambda item: (item["municipio"] or "", item["uf"] or "", item["classe"] or "", item["fonte"] or "", item["periodo_inicio"])):
        group_key = (row["municipio"], row["uf"], row["classe"], row["fonte"])
        cumulative_by_group[group_key] += row["new_mw"]
        row["cumulative_mw"] = cumulative_by_group[group_key]

    metadata = {
        "row_groups_read": row_groups,
        "row_groups_total": parquet_file.num_row_groups,
        "rows_read": rows_read,
        "solar_rows": solar_rows,
        "aggregated_rows": len(aggregated_rows),
    }
    del parquet_file
    return aggregated_rows, metadata


def insert_market_indicators(cur: Any, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    indicator_rows: list[dict[str, Any]] = []
    for row in rows:
        dimensions = {
            "municipio": row["municipio"],
            "uf": row["uf"],
            "classe": row["classe"],
            "fonte": row["fonte"],
        }
        indicator_rows.extend(
            [
                {
                    "indicador_key": "aneel_solar_new_mw",
                    "indicador_nome": "ANEEL solar MW novos",
                    "valor": row["new_mw"],
                    "unidade": "MW",
                    "dimensoes": dimensions,
                    "row": row,
                },
                {
                    "indicador_key": "aneel_solar_cumulative_mw",
                    "indicador_nome": "ANEEL solar MW acumulado",
                    "valor": row["cumulative_mw"],
                    "unidade": "MW",
                    "dimensoes": dimensions,
                    "row": row,
                },
                {
                    "indicador_key": "aneel_solar_new_installations",
                    "indicador_nome": "ANEEL solar novas instalacoes",
                    "valor": row["novas_instalacoes"],
                    "unidade": "instalacoes",
                    "dimensoes": dimensions,
                    "row": row,
                },
            ]
        )
    periods = [row["periodo_inicio"] for row in rows]
    cur.execute(
        """
        delete from public.mercado_indicadores
        where source_key = %s
          and indicador_key in ('aneel_solar_new_mw', 'aneel_solar_cumulative_mw', 'aneel_solar_new_installations')
          and periodo_inicio between %s::date and %s::date
        """,
        (SOURCE_KEY, min(periods), max(periods)),
    )
    cur.executemany(
        """
        insert into public.mercado_indicadores(
          source_key, indicador_key, indicador_nome, periodo_inicio, periodo_label,
          geografia, unidade, valor, dimensoes, payload_original, coletado_em
        )
        values (%s, %s, %s, %s::date, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
        """,
        [
            (
                SOURCE_KEY,
                item["indicador_key"],
                item["indicador_nome"],
                item["row"]["periodo_inicio"],
                item["row"]["periodo_inicio"][:7],
                item["row"]["uf"] or "BR",
                item["unidade"],
                item["valor"],
                json.dumps(item["dimensoes"], ensure_ascii=False),
                json.dumps(item["row"], ensure_ascii=False),
            )
            for item in indicator_rows
        ],
    )
    return len(indicator_rows)


def rollup_for_database(rows: list[dict[str, Any]], *, grain: str) -> list[dict[str, Any]]:
    if grain == "municipio":
        return rows
    rolled: dict[tuple[str, str | None, str | None, str | None], dict[str, Any]] = {}
    for row in rows:
        if month_start(row.get("periodo_inicio")) is None:
            continue
        key = (row["periodo_inicio"], row["uf"], row["classe"], row["fonte"])
        item = rolled.setdefault(
            key,
            {
                "periodo_inicio": row["periodo_inicio"],
                "data_conexao": row["periodo_inicio"],
                "municipio": None,
                "uf": row["uf"],
                "classe": row["classe"],
                "fonte": row["fonte"],
                "potencia_kw": 0.0,
                "novas_instalacoes": 0,
                "data_source": row.get("data_source") or "DthAtualizaCadastralEmpreend",
            },
        )
        item["potencia_kw"] += numeric_value(row.get("potencia_kw"))
        item["novas_instalacoes"] += int(row.get("novas_instalacoes") or 0)

    db_rows = list(rolled.values())
    for row in db_rows:
        row["new_mw"] = row["potencia_kw"] / 1000

    cumulative_by_group: dict[tuple[str | None, str | None, str | None], float] = defaultdict(float)
    for row in sorted(db_rows, key=lambda item: (item["uf"] or "", item["classe"] or "", item["fonte"] or "", item["periodo_inicio"])):
        group_key = (row["uf"], row["classe"], row["fonte"])
        cumulative_by_group[group_key] += row["new_mw"]
        row["cumulative_mw"] = cumulative_by_group[group_key]
    return db_rows


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def persist_rows(
    env: dict[str, str],
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    resource: dict[str, Any],
    *,
    db_grain: str,
    archive_enabled: bool = True,
) -> dict[str, Any]:
    db_rows = rollup_for_database(rows, grain=db_grain)
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(
                cur,
                SOURCE_KEY,
                {
                    **metadata,
                    "resource_id": resource.get("id"),
                    "resource_url": resource.get("url"),
                    "db_grain": db_grain,
                    "db_rows": len(db_rows),
                },
            )
            try:
                archive: dict[str, Any] = {"files": []}
                if archive_enabled:
                    sync_id = f"aneel_solar_{date.today():%Y%m%d}"
                    archive = archive_records(
                        source_system="mercado_api",
                        entity=SOURCE_KEY,
                        sync_id=sync_id,
                        rows=rows,
                        metadata={**metadata, "source_key": SOURCE_KEY, "resource": resource},
                        env=env,
                    )
                require_drive_archive(archive, env=env)
                cur.execute("delete from public.raw_aneel")
                cur.execute("delete from public.fact_solar_monthly")
                cur.execute("delete from public.mercado_indicadores where source_key = %s", (SOURCE_KEY,))
                for batch in chunked(db_rows, 5_000):
                    cur.executemany(
                        """
                        insert into public.raw_aneel(
                          periodo_inicio, data_conexao, municipio, uf, classe, fonte,
                          potencia_kw, novas_instalacoes, payload, coletado_em
                        )
                        values (%s::date, %s::date, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                        on conflict (
                          periodo_inicio, coalesce(municipio, ''), coalesce(uf, ''),
                          coalesce(classe, ''), coalesce(fonte, '')
                        )
                        do update set
                          data_conexao = excluded.data_conexao,
                          potencia_kw = excluded.potencia_kw,
                          novas_instalacoes = excluded.novas_instalacoes,
                          payload = excluded.payload,
                          coletado_em = now()
                        """,
                        [
                            (
                                row["periodo_inicio"],
                                row["data_conexao"],
                                row["municipio"],
                                row["uf"],
                                row["classe"],
                                row["fonte"],
                                row["potencia_kw"],
                                row["novas_instalacoes"],
                                json.dumps(row, ensure_ascii=False),
                            )
                            for row in batch
                        ],
                    )
                    cur.executemany(
                        """
                        insert into public.fact_solar_monthly(
                          periodo_inicio, municipio, uf, classe, fonte,
                          new_mw, cumulative_mw, novas_instalacoes, coletado_em
                        )
                        values (%s::date, %s, %s, %s, %s, %s, %s, %s, now())
                        on conflict (
                          periodo_inicio, coalesce(municipio, ''), coalesce(uf, ''),
                          coalesce(classe, ''), coalesce(fonte, '')
                        )
                        do update set
                          new_mw = excluded.new_mw,
                          cumulative_mw = excluded.cumulative_mw,
                          novas_instalacoes = excluded.novas_instalacoes,
                          coletado_em = now()
                        """,
                        [
                            (
                                row["periodo_inicio"],
                                row["municipio"],
                                row["uf"],
                                row["classe"],
                                row["fonte"],
                                row["new_mw"],
                                row["cumulative_mw"],
                                row["novas_instalacoes"],
                            )
                            for row in batch
                        ],
                    )
                inserted = insert_market_indicators(cur, db_rows)
                found_count = int(metadata.get("solar_rows") or metadata.get("archived_detail_rows") or len(rows))
                finish_run(cur, run_id, status="sucesso", found=found_count, inserted=inserted)
                conn.commit()
                return {
                    "source_key": SOURCE_KEY,
                    "status": "sucesso",
                    "solar_rows": found_count,
                    "archived_detail_rows": len(rows),
                    "db_rows": len(db_rows),
                    "db_grain": db_grain,
                    "indicators_inserted": inserted,
                    "archive_files": len(archive.get("files", [])),
                }
            except Exception as exc:
                found_count = int(metadata.get("solar_rows") or metadata.get("archived_detail_rows") or len(rows))
                finish_run(cur, run_id, status="erro", found=found_count, inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise


def read_archive_rows(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path)
    return frame.where(pd.notna(frame), None).to_dict("records")


def collect_from_archive(path: Path, *, dry_run: bool = False, db_grain: str = "uf") -> dict[str, Any]:
    env = load_env()
    rows = read_archive_rows(path)
    db_rows = rollup_for_database(rows, grain=db_grain)
    metadata = {
        "archive_source": str(path),
        "archived_detail_rows": len(rows),
        "db_grain": db_grain,
        "db_rows": len(db_rows),
        "date_source": "archive",
    }
    if dry_run:
        return {
            "source_key": SOURCE_KEY,
            "status": "dry_run_archive",
            **metadata,
            "sample": rows[:5],
            "db_sample": db_rows[:5],
        }
    return persist_rows(
        env,
        rows,
        metadata,
        {"id": "archive", "url": str(path), "name": path.name},
        db_grain=db_grain,
        archive_enabled=False,
    )


def collect_aneel(*, dry_run: bool = False, max_row_groups: int | None = None, db_grain: str = "uf") -> dict[str, Any]:
    env = load_env()
    resource = discover_general_parquet(env)
    resource_url = str(resource.get("url") or "")
    if not resource_url:
        raise RuntimeError("Recurso ANEEL sem URL.")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        parquet_path = Path(temp_dir) / GENERAL_PARQUET_NAME
        bytes_downloaded = download_file(resource_url, parquet_path, env)
        rows, metadata = aggregate_parquet(parquet_path, max_row_groups=max_row_groups)
        db_rows = rollup_for_database(rows, grain=db_grain)
        metadata = {
            **metadata,
            "bytes_downloaded": bytes_downloaded,
            "resource_id": resource.get("id"),
            "resource_name": resource.get("name"),
            "date_source": "DthAtualizaCadastralEmpreend",
            "db_grain": db_grain,
            "db_rows": len(db_rows),
        }
    if dry_run:
        return {
            "source_key": SOURCE_KEY,
            "status": "dry_run",
            **metadata,
            "sample": rows[:5],
            "db_sample": db_rows[:5],
        }
    return persist_rows(env, rows, metadata, resource, db_grain=db_grain)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta ANEEL geracao distribuida fotovoltaica.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-row-groups", type=int, default=None)
    parser.add_argument("--db-grain", choices=["uf", "municipio"], default=None)
    parser.add_argument("--from-archive-parquet", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    db_grain = args.db_grain or (env.get("ANEEL_DB_GRAIN") or "uf").strip().lower()
    if args.from_archive_parquet:
        result = collect_from_archive(Path(args.from_archive_parquet), dry_run=args.dry_run, db_grain=db_grain)
    else:
        result = collect_aneel(dry_run=args.dry_run, max_row_groups=args.max_row_groups, db_grain=db_grain)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
