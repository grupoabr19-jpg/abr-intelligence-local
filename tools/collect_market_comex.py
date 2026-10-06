from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
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
DEFAULT_API_BASE_URL = "https://api-comexstat.mdic.gov.br"
DEFAULT_STEEL_HEADINGS = {
    "7208": {"familia_abr": "CHAPA FQ", "descricao": "Produtos laminados planos de ferro ou aco nao ligado, a quente"},
    "7209": {"familia_abr": "CHAPA FF", "descricao": "Produtos laminados planos de ferro ou aco nao ligado, a frio"},
    "7210": {"familia_abr": "GALVANIZADA", "descricao": "Produtos laminados planos revestidos"},
    "7216": {"familia_abr": "PERFIS", "descricao": "Perfis de ferro ou aco nao ligado"},
    "7304": {"familia_abr": "TUBOS", "descricao": "Tubos sem costura de ferro ou aco"},
    "7306": {"familia_abr": "TUBOS", "descricao": "Outros tubos e perfis ocos de ferro ou aco"},
}
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


def default_ncm_map_from_api_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ncm_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        ncm = str(row.get("CO_NCM") or "").zfill(8)
        heading = ncm[:4]
        config = DEFAULT_STEEL_HEADINGS.get(heading)
        if not config:
            continue
        ncm_map[ncm] = {
            "descricao": str(row.get("NO_NCM") or row.get("NCM") or config["descricao"]),
            "familia_abr": config["familia_abr"],
            "subfamilia_abr": heading,
        }
    return ncm_map


def csv_url(env: dict[str, str], year: int) -> str:
    base_url = (env.get("COMEX_STAT_CSV_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    return f"{base_url}/IMP_{year}.csv"


def api_base_url(env: dict[str, str]) -> str:
    return (env.get("COMEX_STAT_API_BASE_URL") or DEFAULT_API_BASE_URL).strip().rstrip("/")


def api_month_range(year: int) -> tuple[str, str]:
    today = date.today()
    end_month = 12
    if year == today.year:
        end_month = max(1, today.month - 1)
    return f"{year}-01", f"{year}-{end_month:02d}"


def post_comex_api(client: httpx.Client, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    last_error = ""
    for attempt in range(6):
        response = client.post(url, params={"language": "pt"}, json=payload)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        last_error = response.text[:300]
        time.sleep(10 + attempt * 5)
    raise RuntimeError(f"Comex API rate limit persistente: {last_error}")


def text_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def numeric_api_value(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        return 0.0
    text = str(value).strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def api_row_to_legacy(row: dict[str, Any]) -> dict[str, Any] | None:
    year = text_value(row, "year", "coAno", "CO_ANO")
    month = text_value(row, "monthNumber", "month", "CO_MES")
    ncm = "".join(char for char in text_value(row, "ncm", "coNcm", "CO_NCM").split(" - ", 1)[0] if char.isdigit())
    if not ncm:
        heading = "".join(char for char in text_value(row, "headingCode", "heading", "coSh4", "CO_SH4").split(" - ", 1)[0] if char.isdigit())
        ncm = f"{heading[:4]}0000" if heading else ""
    if not year or not month or not ncm:
        return None
    return {
        "CO_ANO": int(year),
        "CO_MES": int(month),
        "CO_NCM": ncm.zfill(8),
        "NO_NCM": text_value(row, "ncm", "ncmDescription", "heading", "NO_NCM"),
        "CO_UNID": "",
        "CO_PAIS": text_value(row, "country", "coPais", "CO_PAIS"),
        "SG_UF_NCM": text_value(row, "state", "sgUfNcm", "SG_UF_NCM"),
        "CO_VIA": text_value(row, "via", "coVia", "CO_VIA"),
        "CO_URF": text_value(row, "urf", "coUrf", "CO_URF"),
        "QT_ESTAT": numeric_api_value(row, "metricStatistic"),
        "KG_LIQUIDO": numeric_api_value(row, "metricKG"),
        "VL_FOB": numeric_api_value(row, "metricFOB"),
        "VL_FRETE": numeric_api_value(row, "metricFreight"),
        "VL_SEGURO": numeric_api_value(row, "metricInsurance"),
        "VL_CIF": numeric_api_value(row, "metricCIF"),
    }


def fetch_api_rows(env: dict[str, str], year: int, ncm_map: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_url = api_base_url(env)
    url = f"{base_url}/general"
    period_from, period_to = api_month_range(year)
    headings = sorted({ncm[:4] for ncm in ncm_map} or DEFAULT_STEEL_HEADINGS.keys())
    chapters = sorted({heading[:2] for heading in headings})
    rows: list[dict[str, Any]] = []
    metadata = {"url": url, "period": {"from": period_from, "to": period_to}, "headings": headings, "chapters": chapters}
    headers = {"user-agent": env.get("EXTERNAL_DATA_USER_AGENT") or "ABR-Intelligence/1.0"}
    with httpx.Client(timeout=90, follow_redirects=True, headers=headers) as client:
        for chapter in chapters:
            payload = {
                "flow": "import",
                "monthDetail": True,
                "period": {"from": period_from, "to": period_to},
                "filters": [{"filter": "chapter", "values": [chapter]}],
                "details": ["heading", "state"],
                "metrics": ["metricFOB", "metricKG", "metricFreight", "metricInsurance", "metricCIF"],
            }
            data = post_comex_api(client, url, payload)
            for item in data.get("data", {}).get("list", []):
                legacy = api_row_to_legacy(item)
                if legacy and str(legacy["CO_NCM"]).zfill(8)[:4] in headings:
                    rows.append(legacy)
    return rows, metadata


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


def upsert_ncm_dimension(cur: Any, ncm_map: dict[str, dict[str, Any]]) -> int:
    if not ncm_map:
        return 0
    cur.executemany(
        """
        insert into public.dim_ncm_abr(
          ncm, descricao, familia_abr, subfamilia_abr, ativo, validado_por, observacoes, atualizado_em
        )
        values (%s, %s, %s, %s, true, 'sistema', %s, now())
        on conflict (ncm) do update set
          descricao = excluded.descricao,
          familia_abr = excluded.familia_abr,
          subfamilia_abr = excluded.subfamilia_abr,
          ativo = true,
          observacoes = excluded.observacoes,
          atualizado_em = now()
        """,
        [
            (
                ncm,
                values.get("descricao") or ncm,
                values["familia_abr"],
                values.get("subfamilia_abr"),
                "Mapeamento tecnico por SH4 usado pela API ComexStat para radar de importacao.",
            )
            for ncm, values in sorted(ncm_map.items())
        ],
    )
    return len(ncm_map)


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


def collect_comex(year: int, dry_run: bool = False, source: str = "api") -> dict[str, Any]:
    env = load_env()
    url = api_base_url(env) if source == "api" else csv_url(env, year)
    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            ncm_map = load_active_ncm(cur)
            if not ncm_map and source != "api":
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

    byte_size = 0
    metadata: dict[str, Any] = {"year": year, "url": url, "source": source}
    if source == "api":
        filtered, api_metadata = fetch_api_rows(env, year, ncm_map)
        metadata.update(api_metadata)
        if not ncm_map:
            ncm_map = default_ncm_map_from_api_rows(filtered)
        filtered = [row for row in filtered if str(row["CO_NCM"]).zfill(8) in ncm_map]
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / f"IMP_{year}.csv"
            byte_size = 0 if dry_run else download_csv(url, csv_path)
            filtered = []
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
            "source": source,
            "approved_ncms": len(ncm_map),
            "filtered_rows": len(filtered),
            "fact_rows": len(fact_rows),
            "sample": fact_rows[:5],
        }

    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(cur, {**metadata, "approved_ncms": len(ncm_map), "download_bytes": byte_size})
            try:
                archive = archive_records(
                    source_system="mercado_api",
                    entity=SOURCE_KEY,
                    sync_id=f"comex_imp_{source}_{year}",
                    rows=filtered,
                    metadata={**metadata, "source_key": SOURCE_KEY, "approved_ncms": len(ncm_map)},
                    env=env,
                )
                require_drive_archive(archive, env=env)
                raw_inserted = insert_raw(cur, filtered)
                ncm_upserted = upsert_ncm_dimension(cur, ncm_map)
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
                    "source": source,
                    "ncm_dimension_rows": ncm_upserted,
                    "raw_rows": raw_inserted,
                    "fact_rows": fact_inserted,
                    "indicators_inserted": indicator_inserted,
                    "archive_files": len(archive.get("files", [])),
                }
            except Exception as exc:
                conn.rollback()
                with conn.cursor() as error_cur:
                    finish_run(error_cur, run_id, status="erro", found=len(filtered), inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta Comex Stat IMP por NCM aprovado.")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--source", choices=("api", "csv"), default="api")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = collect_comex(args.year, dry_run=args.dry_run, source=args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
