from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


DEFAULT_TIMEOUT = 60
SOURCE_SYSTEM = "GOOGLE_SHEETS"
ENTITY = "atendimento_kommo"


def sheet_csv_url(env: dict[str, str]) -> str:
    if env.get("KOMMO_ATENDIMENTO_EXPORT_CSV_URL"):
        return env["KOMMO_ATENDIMENTO_EXPORT_CSV_URL"]
    sheet_id = env.get("KOMMO_ATENDIMENTO_SHEET_ID")
    if not sheet_id:
        raise SystemExit("Configure KOMMO_ATENDIMENTO_EXPORT_CSV_URL ou KOMMO_ATENDIMENTO_SHEET_ID no .env.")
    gid = env.get("KOMMO_ATENDIMENTO_SHEET_GID", "0")
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key or "").strip(): str(value or "").strip() for key, value in row.items() if str(key or "").strip()}


def row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def fetch_rows(url: str, timeout: int) -> list[dict[str, Any]]:
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        text = response.content.decode(encoding, errors="replace")
        if "�" not in text[:1000]:
            break
    if "html" in content_type.lower() and "<html" in text[:500].lower():
        raise SystemExit(
            "A URL retornou HTML, nao CSV. Verifique se a planilha esta publica ou configure uma URL /export?format=csv."
        )
    reader = csv.DictReader(StringIO(text))
    return [normalized_row(row) for row in reader if any(str(value or "").strip() for value in row.values())]


def insert_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    env = load_env()
    sync_id = f"kommo_atendimento_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    inserted = 0
    skipped = 0
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            for index, row in enumerate(rows, start=1):
                hash_value = row_hash(row)
                cur.execute(
                    """
                    insert into public.staging_dados(
                      source_system,
                      source_id,
                      entidade,
                      payload_original,
                      dados_transformados,
                      sync_id,
                      hash_registro,
                      status_validacao,
                      tabela_destino,
                      ativo
                    )
                    select %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, 'pendente', 'atendimento_kommo', true
                    where not exists (
                      select 1
                      from public.staging_dados
                      where source_system = %s
                        and entidade = %s
                        and hash_registro = %s
                    )
                    """,
                    (
                        SOURCE_SYSTEM,
                        f"{ENTITY}:{index}",
                        ENTITY,
                        json.dumps(row, ensure_ascii=False),
                        json.dumps(row, ensure_ascii=False),
                        sync_id,
                        hash_value,
                        SOURCE_SYSTEM,
                        ENTITY,
                        hash_value,
                    ),
                )
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
            conn.commit()
    return {"inserted": inserted, "skipped": skipped}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta dados de atendimento Kommo via Google Sheets CSV.")
    parser.add_argument("--dry-run", action="store_true", help="Le a planilha e mostra resumo sem gravar.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    timeout = int(env.get("EXTERNAL_DATA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
    url = sheet_csv_url(env)
    rows = fetch_rows(url, timeout)
    result: dict[str, Any] = {
        "url": url,
        "rows_found": len(rows),
        "headers": list(rows[0].keys()) if rows else [],
        "sample": rows[:3],
    }
    if not args.dry_run:
        result.update(insert_rows(rows))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
