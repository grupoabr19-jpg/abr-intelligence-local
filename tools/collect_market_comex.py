from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.archive_storage import archive_records, require_drive_archive
from tools.apply_migrations import connect_market_database, load_env
from tools.market_indicator_quality import normalize_and_validate_indicators


SOURCE_KEY = "comex_stat_ncm"
DEFAULT_BASE_URL = "https://balanca.mdic.gov.br/balanca/bd/comexstat-bd/ncm"
REQUIRED_COLUMNS = (
    "CO_ANO",
    "CO_MES",
    "CO_NCM",
    "CO_UNID",
    "CO_PAIS",
    "SG_UF_NCM",
    "CO_VIA",
    "CO_URF",
    "QT_ESTAT",
    "KG_LIQUIDO",
    "VL_FOB",
    "VL_FRETE",
    "VL_SEGURO",
)


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


def finish_run(cur: Any, run_id: str, *, status: str, found: int, inserted: int, error: str | None = None) -> None:
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


def load_active_ncm(cur: Any) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        select ncm, descricao, familia_abr, subfamilia_abr
        from public.dim_ncm_abr
        where ativo = true
          and (vigencia_inicio is null or vigencia_inicio <= current_date)
          and (vigencia_fim is null or vigencia_fim >= current_date)
        """
    )
    return {
        str(row[0]).zfill(8): {
            "descricao": row[1],
            "familia_abr": row[2],
            "subfamilia_abr": row[3],
        }
        for row in cur.fetchall()
    }


def csv_url(env: dict[str, str], year: int) -> str:
    base_url = (env.get("COMEX_STAT_CSV_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    return f"{base_url}/IMP_{year}.csv"


def download_csv(url: str, target: Path) -> int:
    headers = {"user-agent": "ABR-Intelligence/1.0"}
    try:
        client = httpx.Client(timeout=900, follow_redirects=True, headers=headers)
        response = client.get(url)
        response.raise_for_status()
        target.write_bytes(response.content)
    except httpx.ConnectError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        with httpx.Client(timeout=900, follow_redirects=True, headers=headers, verify=False) as fallback:
            response = fallback.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)
    finally:
        if "client" in locals():
            client.close()
    return target.stat().st_size


def number_or_zero(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def filtered_rows(frame: pd.DataFrame, ncm_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    frame = frame.copy()
    frame["CO_NCM"] = frame["CO_NCM"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(8)
    frame = frame[frame["CO_NCM"].isin(ncm_map.keys())]
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        row = {key: record.get(key) for key in REQUIRED_COLUMNS}
        rows.append(row)
    return rows


def insert_raw(cur: Any, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    cur.executemany(
        """
        insert into public.raw_comex_import(
          co_ano, co_mes, co_ncm, co_unid, co_pais, sg_uf_ncm, co_via, co_urf,
          qt_estat, kg_liquido, vl_fob, vl_frete, vl_seguro, payload, coletado_em
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
        on conflict (co_ano, co_mes, co_ncm, co_pais, sg_uf_ncm, co_via, co_urf)
        do update set
          co_unid = excluded.co_unid,
          qt_estat = excluded.qt_estat,
          kg_liquido = excluded.kg_liquido,
          vl_fob = excluded.vl_fob,
          vl_frete = excluded.vl_frete,
          vl_seguro = excluded.vl_seguro,
          payload = excluded.payload,
          coletado_em = now()
        """,
        [
            (
                int(row["CO_ANO"]),
                int(row["CO_MES"]),
                str(row["CO_NCM"]).zfill(8),
                str(row.get("CO_UNID") or ""),
                str(row.get("CO_PAIS") or ""),
                str(row.get("SG_UF_NCM") or ""),
                str(row.get("CO_VIA") or ""),
                str(row.get("CO_URF") or ""),
                number_or_zero(row.get("QT_ESTAT")),
                number_or_zero(row.get("KG_LIQUIDO")),
                number_or_zero(row.get("VL_FOB")),
                number_or_zero(row.get("VL_FRETE")),
                number_or_zero(row.get("VL_SEGURO")),
                json.dumps(row, ensure_ascii=False),
            )
            for row in rows
        ],
    )
    return len(rows)


def refresh_fact(cur: Any, rows: list[dict[str, Any]], ncm_map: dict[str, dict[str, Any]]) -> int:
    if not rows:
        return 0
    aggregate: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        ncm = str(row["CO_NCM"]).zfill(8)
        period = f"{int(row['CO_ANO']):04d}-{int(row['CO_MES']):02d}-01"
        key = (period, ncm, str(row.get("SG_UF_NCM") or ""), str(row.get("CO_PAIS") or ""))
        item = aggregate.setdefault(
            key,
            {
                "periodo_inicio": period,
                "ncm": ncm,
                "familia_abr": ncm_map[ncm]["familia_abr"],
                "subfamilia_abr": ncm_map[ncm].get("subfamilia_abr"),
                "sg_uf_ncm": str(row.get("SG_UF_NCM") or ""),
                "co_pais": str(row.get("CO_PAIS") or ""),
                "toneladas": 0.0,
                "vl_fob_usd": 0.0,
                "vl_frete_usd": 0.0,
                "vl_seguro_usd": 0.0,
            },
        )
        item["toneladas"] += number_or_zero(row.get("KG_LIQUIDO")) / 1000
        item["vl_fob_usd"] += number_or_zero(row.get("VL_FOB"))
        item["vl_frete_usd"] += number_or_zero(row.get("VL_FRETE"))
        item["vl_seguro_usd"] += number_or_zero(row.get("VL_SEGURO"))

    fact_rows = []
    for item in aggregate.values():
        tons = item["toneladas"]
        fob_usd_t = item["vl_fob_usd"] / tons if tons else None
        cif_proxy_usd_t = (item["vl_fob_usd"] + item["vl_frete_usd"] + item["vl_seguro_usd"]) / tons if tons else None
        fact_rows.append({**item, "fob_usd_t": fob_usd_t, "cif_proxy_usd_t": cif_proxy_usd_t})

    cur.executemany(
        """
        insert into public.fact_steel_import_monthly(
          periodo_inicio, ncm, familia_abr, subfamilia_abr, sg_uf_ncm, co_pais,
          toneladas, vl_fob_usd, vl_frete_usd, vl_seguro_usd,
          fob_usd_t, cif_proxy_usd_t, coletado_em
        )
        values (%s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (periodo_inicio, ncm, coalesce(sg_uf_ncm, ''), coalesce(co_pais, ''))
        do update set
          familia_abr = excluded.familia_abr,
          subfamilia_abr = excluded.subfamilia_abr,
          toneladas = excluded.toneladas,
          vl_fob_usd = excluded.vl_fob_usd,
          vl_frete_usd = excluded.vl_frete_usd,
          vl_seguro_usd = excluded.vl_seguro_usd,
          fob_usd_t = excluded.fob_usd_t,
          cif_proxy_usd_t = excluded.cif_proxy_usd_t,
          coletado_em = now()
        """,
        [
            (
                row["periodo_inicio"],
                row["ncm"],
                row["familia_abr"],
                row.get("subfamilia_abr"),
                row.get("sg_uf_ncm"),
                row.get("co_pais"),
                row["toneladas"],
                row["vl_fob_usd"],
                row["vl_frete_usd"],
                row["vl_seguro_usd"],
                row["fob_usd_t"],
                row["cif_proxy_usd_t"],
            )
            for row in fact_rows
        ],
    )
    return len(fact_rows)


def insert_indicators(cur: Any, fact_rows: list[dict[str, Any]]) -> int:
    if not fact_rows:
        return 0
    indicator_rows: list[dict[str, Any]] = []
    for row in fact_rows:
        dimensions = {
            "ncm": row["ncm"],
            "familia_abr": row["familia_abr"],
            "subfamilia_abr": row.get("subfamilia_abr"),
            "sg_uf_ncm": row.get("sg_uf_ncm"),
            "co_pais": row.get("co_pais"),
        }
        metrics = (
            ("comex_import_toneladas", "Importacoes Comex", "t", row["toneladas"]),
            ("comex_import_fob_usd_t", "FOB medio importado", "US$/t", row["fob_usd_t"]),
            ("comex_import_cif_proxy_usd_t", "CIF proxy importado", "US$/t", row["cif_proxy_usd_t"]),
        )
        for key, name, unit, value in metrics:
            if value is None:
                continue
            indicator_rows.append(
                {
                    "source_key": SOURCE_KEY,
                    "indicador_key": key,
                    "indicador_nome": name,
                    "periodo_inicio": row["periodo_inicio"],
                    "periodo_label": row["periodo_inicio"][:7],
                    "geografia": "BR",
                    "unidade": unit,
                    "valor": value,
                    "dimensoes": dimensions,
                    "payload_original": row,
                }
            )
    indicator_rows = normalize_and_validate_indicators(cur, indicator_rows)
    if not indicator_rows:
        return 0
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
                row["source_key"],
                row["indicador_key"],
                row["indicador_nome"],
                row["periodo_inicio"],
                row["periodo_label"],
                row.get("geografia", "BR"),
                row["unidade"],
                row["valor"],
                json.dumps(row.get("dimensoes", {}), ensure_ascii=False),
                json.dumps(row.get("payload_original", {}), ensure_ascii=False),
            )
            for row in indicator_rows
        ],
    )
    return len(indicator_rows)


def aggregate_fact_rows(rows: list[dict[str, Any]], ncm_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    aggregate: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        ncm = str(row["CO_NCM"]).zfill(8)
        period = f"{int(row['CO_ANO']):04d}-{int(row['CO_MES']):02d}-01"
        key = (period, ncm, str(row.get("SG_UF_NCM") or ""), str(row.get("CO_PAIS") or ""))
        item = aggregate.setdefault(
            key,
            {
                "periodo_inicio": period,
                "ncm": ncm,
                "familia_abr": ncm_map[ncm]["familia_abr"],
                "subfamilia_abr": ncm_map[ncm].get("subfamilia_abr"),
                "sg_uf_ncm": str(row.get("SG_UF_NCM") or ""),
                "co_pais": str(row.get("CO_PAIS") or ""),
                "toneladas": 0.0,
                "vl_fob_usd": 0.0,
                "vl_frete_usd": 0.0,
                "vl_seguro_usd": 0.0,
            },
        )
        item["toneladas"] += number_or_zero(row.get("KG_LIQUIDO")) / 1000
        item["vl_fob_usd"] += number_or_zero(row.get("VL_FOB"))
        item["vl_frete_usd"] += number_or_zero(row.get("VL_FRETE"))
        item["vl_seguro_usd"] += number_or_zero(row.get("VL_SEGURO"))
    fact_rows = []
    for item in aggregate.values():
        tons = item["toneladas"]
        fact_rows.append(
            {
                **item,
                "fob_usd_t": item["vl_fob_usd"] / tons if tons else None,
                "cif_proxy_usd_t": (item["vl_fob_usd"] + item["vl_frete_usd"] + item["vl_seguro_usd"]) / tons if tons else None,
            }
        )
    return fact_rows


def collect_comex(year: int, dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    url = csv_url(env, year)
    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            ncm_map = load_active_ncm(cur)
            if not ncm_map:
                if not dry_run:
                    run_id = start_run(cur, {"year": year, "url": url, "reason": "dim_ncm_abr vazia"})
                    finish_run(
                        cur,
                        run_id,
                        status="parcial",
                        found=0,
                        inserted=0,
                        error="Nenhum NCM ativo aprovado em dim_ncm_abr. Comex nao foi baixado para evitar dado inventado.",
                    )
                    conn.commit()
                return {
                    "source_key": SOURCE_KEY,
                    "status": "sem_ncm_aprovado",
                    "year": year,
                    "message": "Cadastre NCMs ativos em dim_ncm_abr antes de processar Comex.",
                }

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / f"IMP_{year}.csv"
        byte_size = 0 if dry_run else download_csv(url, csv_path)
        filtered: list[dict[str, Any]] = []
        chunks = pd.read_csv(
            csv_path if not dry_run else url,
            sep=";",
            encoding="latin1",
            usecols=list(REQUIRED_COLUMNS),
            chunksize=100_000,
            dtype={"CO_NCM": "string", "SG_UF_NCM": "string", "CO_PAIS": "string", "CO_VIA": "string", "CO_URF": "string"},
        )
        for frame in chunks:
            filtered.extend(filtered_rows(frame, ncm_map))

    fact_rows = aggregate_fact_rows(filtered, ncm_map)
    if dry_run:
        return {
            "source_key": SOURCE_KEY,
            "status": "dry_run",
            "year": year,
            "approved_ncms": len(ncm_map),
            "filtered_rows": len(filtered),
            "fact_rows": len(fact_rows),
            "sample": fact_rows[:5],
        }

    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(cur, {"year": year, "url": url, "approved_ncms": len(ncm_map), "download_bytes": byte_size})
            try:
                archive = archive_records(
                    source_system="mercado_api",
                    entity=SOURCE_KEY,
                    sync_id=f"comex_imp_{year}",
                    rows=filtered,
                    metadata={"source_key": SOURCE_KEY, "url": url, "year": year, "approved_ncms": len(ncm_map)},
                    env=env,
                )
                require_drive_archive(archive, env=env)
                raw_inserted = insert_raw(cur, filtered)
                periods = sorted({row["periodo_inicio"] for row in fact_rows})
                if periods:
                    cur.execute(
                        """
                        delete from public.mercado_indicadores
                        where source_key = %s
                          and indicador_key in ('comex_import_toneladas', 'comex_import_fob_usd_t', 'comex_import_cif_proxy_usd_t')
                          and periodo_inicio between %s::date and %s::date
                        """,
                        (SOURCE_KEY, min(periods), max(periods)),
                    )
                fact_inserted = refresh_fact(cur, filtered, ncm_map)
                indicator_inserted = insert_indicators(cur, fact_rows)
                finish_run(cur, run_id, status="sucesso", found=len(filtered), inserted=indicator_inserted)
                conn.commit()
                return {
                    "source_key": SOURCE_KEY,
                    "status": "sucesso",
                    "year": year,
                    "raw_rows": raw_inserted,
                    "fact_rows": fact_inserted,
                    "indicators_inserted": indicator_inserted,
                    "archive_files": len(archive.get("files", [])),
                }
            except Exception as exc:
                finish_run(cur, run_id, status="erro", found=len(filtered), inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta Comex Stat IMP por NCM aprovado.")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = collect_comex(args.year, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
