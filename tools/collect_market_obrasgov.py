from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
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


SOURCE_KEY = "obrasgov_projetos"
DEFAULT_BASE_URL = "https://api-publica.obrasgov.gestao.gov.br/obras"


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


def numeric_value(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def investimento_previsto(row: dict[str, Any]) -> float:
    investimentos = row.get("investimentos_previstos")
    if not isinstance(investimentos, list):
        return 0.0
    return sum(numeric_value(item.get("vl_investimento_previsto")) for item in investimentos if isinstance(item, dict))


def eixo_principal(row: dict[str, Any]) -> str | None:
    eixos = row.get("eixos_tipos")
    if isinstance(eixos, list) and eixos and isinstance(eixos[0], dict):
        return clean_text(eixos[0].get("eixo"))
    return None


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=20), reraise=True)
def fetch_page(base_url: str, year: int, page: int, page_size: int) -> dict[str, Any]:
    with httpx.Client(timeout=90, follow_redirects=True, headers={"user-agent": "ABR-Intelligence/1.0"}) as client:
        response = client.get(
            f"{base_url.rstrip('/')}/projeto-investimento",
            params={"ano_cadastro": year, "pagina": page, "tamanho_da_pagina": page_size},
        )
        response.raise_for_status()
        return response.json()


def collect_pages(base_url: str, years: list[int], page_size: int, max_pages: int | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {"years": years, "page_size": page_size, "pages_read": 0, "total_items_reported": 0}
    for year in years:
        first = fetch_page(base_url, year, 1, page_size)
        total_pages = int(first.get("total_pages") or 1)
        total_items = int(first.get("total_items") or 0)
        pages_to_read = min(total_pages, max_pages) if max_pages else total_pages
        metadata["total_items_reported"] += total_items
        rows.extend(first.get("data") or [])
        metadata["pages_read"] += 1
        for page in range(2, pages_to_read + 1):
            payload = fetch_page(base_url, year, page, page_size)
            rows.extend(payload.get("data") or [])
            metadata["pages_read"] += 1
    return rows, metadata


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str | None, str | None, str | None, str | None], dict[str, Any]] = {}
    for row in rows:
        year = row.get("ano_cadastro")
        if not isinstance(year, int):
            continue
        key = (
            year,
            clean_text(row.get("uf_principal")),
            clean_text(row.get("situacao")),
            clean_text(row.get("natureza_intervencao")),
            eixo_principal(row),
        )
        item = grouped.setdefault(
            key,
            {
                "ano_cadastro": key[0],
                "uf": key[1],
                "situacao": key[2],
                "natureza_intervencao": key[3],
                "eixo": key[4],
                "projetos": 0,
                "investimento_previsto": 0.0,
                "empregos_gerados": 0.0,
            },
        )
        item["projetos"] += 1
        item["investimento_previsto"] += investimento_previsto(row)
        item["empregos_gerados"] += numeric_value(row.get("qtd_empregos_gerados"))
    return list(grouped.values())


def indicator_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        periodo = f"{row['ano_cadastro']}-01-01"
        dimensoes = {
            "uf": row["uf"],
            "situacao": row["situacao"],
            "natureza_intervencao": row["natureza_intervencao"],
            "eixo": row["eixo"],
        }
        metrics = [
            ("obrasgov_projetos", "ObrasGov projetos", row["projetos"], "projetos"),
            ("obrasgov_investimento_previsto", "ObrasGov investimento previsto", row["investimento_previsto"], "BRL"),
            ("obrasgov_empregos_gerados", "ObrasGov empregos gerados", row["empregos_gerados"], "empregos"),
        ]
        for key, name, value, unit in metrics:
            output.append(
                {
                    "source_key": SOURCE_KEY,
                    "indicador_key": key,
                    "indicador_nome": name,
                    "periodo_inicio": periodo,
                    "periodo_label": str(row["ano_cadastro"]),
                    "geografia": row["uf"] or "BR",
                    "unidade": unit,
                    "valor": value,
                    "dimensoes": dimensoes,
                    "payload_original": row,
                }
            )
    return output


def collect_obrasgov(*, dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    base_url = env.get("OBRASGOV_API_BASE_URL") or DEFAULT_BASE_URL
    years = [int(item.strip()) for item in (env.get("OBRASGOV_YEARS") or str(date.today().year)).split(";") if item.strip()]
    page_size = min(int(env.get("OBRASGOV_PAGE_SIZE") or "200"), 200)
    max_pages_text = (env.get("OBRASGOV_MAX_PAGES") or "25").strip()
    max_pages = int(max_pages_text) if max_pages_text else None
    raw_rows, metadata = collect_pages(base_url, years, page_size, max_pages)
    aggregates = aggregate_rows(raw_rows)
    indicators = indicator_rows(aggregates)
    if dry_run:
        return {
            "source_key": SOURCE_KEY,
            "status": "dry_run",
            "records_found": len(raw_rows),
            "aggregated_rows": len(aggregates),
            "indicators_found": len(indicators),
            **metadata,
            "sample": aggregates[:5],
        }

    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(cur, {**metadata, "base_url": base_url})
            try:
                archive = archive_records(
                    source_system="mercado_api",
                    entity=SOURCE_KEY,
                    sync_id=f"obrasgov_{date.today():%Y%m%d}",
                    rows=raw_rows,
                    metadata={"source_key": SOURCE_KEY, "base_url": base_url, **metadata},
                    env=env,
                )
                require_drive_archive(archive, env=env)
                cur.execute("delete from public.raw_obrasgov_project_summary")
                cur.execute("delete from public.fact_obrasgov_investments")
                cur.execute("delete from public.mercado_indicadores where source_key = %s", (SOURCE_KEY,))
                cur.executemany(
                    """
                    insert into public.raw_obrasgov_project_summary(
                      ano_cadastro, uf, situacao, natureza_intervencao, eixo,
                      projetos, investimento_previsto, empregos_gerados, payload, coletado_em
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                    on conflict (
                      ano_cadastro, coalesce(uf, ''), coalesce(situacao, ''),
                      coalesce(natureza_intervencao, ''), coalesce(eixo, '')
                    )
                    do update set
                      projetos = excluded.projetos,
                      investimento_previsto = excluded.investimento_previsto,
                      empregos_gerados = excluded.empregos_gerados,
                      payload = excluded.payload,
                      coletado_em = now()
                    """,
                    [
                        (
                            row["ano_cadastro"],
                            row["uf"],
                            row["situacao"],
                            row["natureza_intervencao"],
                            row["eixo"],
                            row["projetos"],
                            row["investimento_previsto"],
                            row["empregos_gerados"],
                            json.dumps(row, ensure_ascii=False),
                        )
                        for row in aggregates
                    ],
                )
                cur.executemany(
                    """
                    insert into public.fact_obrasgov_investments(
                      periodo_inicio, uf, situacao, natureza_intervencao, eixo,
                      projetos, investimento_previsto, empregos_gerados, coletado_em
                    )
                    values (%s::date, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (
                      periodo_inicio, coalesce(uf, ''), coalesce(situacao, ''),
                      coalesce(natureza_intervencao, ''), coalesce(eixo, '')
                    )
                    do update set
                      projetos = excluded.projetos,
                      investimento_previsto = excluded.investimento_previsto,
                      empregos_gerados = excluded.empregos_gerados,
                      coletado_em = now()
                    """,
                    [
                        (
                            f"{row['ano_cadastro']}-01-01",
                            row["uf"],
                            row["situacao"],
                            row["natureza_intervencao"],
                            row["eixo"],
                            row["projetos"],
                            row["investimento_previsto"],
                            row["empregos_gerados"],
                        )
                        for row in aggregates
                    ],
                )
                indicators = normalize_and_validate_indicators(cur, indicators)
                if indicators:
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
                            for row in indicators
                        ],
                    )
                finish_run(cur, run_id, status="sucesso", found=len(raw_rows), inserted=len(indicators))
                conn.commit()
                return {
                    "source_key": SOURCE_KEY,
                    "status": "sucesso",
                    "records_found": len(raw_rows),
                    "aggregated_rows": len(aggregates),
                    "indicators_inserted": len(indicators),
                    "archive_files": len(archive.get("files", [])),
                }
            except Exception as exc:
                finish_run(cur, run_id, status="erro", found=len(raw_rows), inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta projetos de investimento ObrasGov.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = collect_obrasgov(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
