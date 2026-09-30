from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from psycopg.types.json import Json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.archive_storage import (  # noqa: E402
    DRIVE_FOLDER_MIME,
    archive_config,
    download_drive_file,
    drive_access_token,
    export_drive_file,
    file_sha256,
    list_drive_children,
    slug,
)
from backend.aster_collector.local_spreadsheets import HEADER_ROWS  # noqa: E402
from tools.apply_migrations import connect_database, load_env  # noqa: E402


GOOGLE_SHEETS_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MIME_TYPES = {"text/csv", "application/csv", "text/plain"}
SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm", ".csv"}
DEFAULT_SCAN_DEPTH = int(os.environ.get("DRIVE_SPREADSHEET_SCAN_DEPTH", "1") or "1")
GENERATED_ARCHIVE_SUFFIXES = (
    "_clean.csv",
    "_raw.jsonl",
    "_clean.parquet",
    "_manifest.json",
    ".csv.gz",
    ".jsonl",
    ".parquet",
)


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " / ").strip()


def file_key(file_info: dict[str, Any]) -> str:
    modified = file_info.get("modifiedTime") or "sem_data"
    return f"{file_info['id']}:{modified}"


def is_supported_spreadsheet(file_info: dict[str, Any]) -> bool:
    mime_type = file_info.get("mimeType") or ""
    name = file_info.get("name") or ""
    lowered = name.lower()
    if any(lowered.endswith(suffix) for suffix in GENERATED_ARCHIVE_SUFFIXES):
        return False
    suffix = Path(name).suffix.lower()
    return mime_type == GOOGLE_SHEETS_MIME or mime_type == XLSX_MIME or mime_type in CSV_MIME_TYPES or suffix in SUPPORTED_EXTENSIONS


def list_spreadsheets_recursive(token: str, root_folder_id: str, *, max_depth: int = 5) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    queue: list[tuple[str, int]] = [(root_folder_id, 0)]
    seen_folders: set[str] = set()
    while queue:
        folder_id, depth = queue.pop(0)
        if folder_id in seen_folders or depth > max_depth:
            continue
        seen_folders.add(folder_id)
        for child in list_drive_children(token, folder_id):
            mime_type = child.get("mimeType")
            if mime_type == DRIVE_FOLDER_MIME:
                queue.append((child["id"], depth + 1))
                continue
            if is_supported_spreadsheet(child):
                child["parent_id"] = folder_id
                found.append(child)
    return found


def already_processed(cur: Any, file_info: dict[str, Any]) -> bool:
    cur.execute(
        """
        select 1
        from public.drive_spreadsheet_ingestions
        where drive_file_id = %s
          and drive_modified_time = %s::timestamptz
          and status = 'sucesso'
        limit 1
        """,
        (file_info["id"], file_info.get("modifiedTime")),
    )
    return cur.fetchone() is not None


def start_ingestion(cur: Any, file_info: dict[str, Any], sync_id: str, local_path: Path | None = None) -> str:
    cur.execute(
        """
        insert into public.drive_spreadsheet_ingestions(
          drive_file_id, drive_file_name, drive_mime_type, drive_modified_time,
          drive_parent_id, local_path, sync_id, metadata
        )
        values (%s, %s, %s, %s::timestamptz, %s, %s, %s, %s::jsonb)
        on conflict (drive_file_id, drive_modified_time)
        do update set
          status = 'processando',
          sync_id = excluded.sync_id,
          started_at = now(),
          finished_at = null,
          error_message = null,
          local_path = excluded.local_path
        returning id::text
        """,
        (
            file_info["id"],
            file_info.get("name"),
            file_info.get("mimeType"),
            file_info.get("modifiedTime"),
            file_info.get("parent_id"),
            str(local_path.relative_to(ROOT)) if local_path else None,
            sync_id,
            Json({"webViewLink": file_info.get("webViewLink"), "size": file_info.get("size")}),
        ),
    )
    return str(cur.fetchone()[0])


def finish_ingestion(
    cur: Any,
    ingestion_id: str,
    *,
    status: str,
    rows_read: int = 0,
    rows_inserted: int = 0,
    worksheets: list[dict[str, Any]] | None = None,
    file_hash: str | None = None,
    detected_type: str = "GERAL",
    error_message: str | None = None,
) -> None:
    cur.execute(
        """
        update public.drive_spreadsheet_ingestions
        set status = %s,
            rows_read = %s,
            rows_inserted = %s,
            worksheets = %s::jsonb,
            file_sha256 = %s,
            detected_type = %s,
            error_message = %s,
            finished_at = now()
        where id = %s::uuid
        """,
        (
            status,
            rows_read,
            rows_inserted,
            Json(worksheets or []),
            file_hash,
            detected_type,
            error_message,
            ingestion_id,
        ),
    )


def detect_type(file_name: str, sheets: list[str]) -> str:
    probe = f"{file_name} {' '.join(sheets)}".lower()
    if "gest" in probe and ("produ" in probe or "prod" in probe):
        return "GESTAO_PRODUCAO"
    if "margem" in probe or "gabr" in probe:
        return "MARGEM"
    if "ranking" in probe:
        return "RANKING"
    if "estoque" in probe:
        return "ESTOQUE"
    if "cliente" in probe:
        return "CLIENTES"
    return "GERAL"


def infer_header_row(file_name: str, sheet_name: str, preview_rows: list[tuple[Any, ...]]) -> int:
    configured = HEADER_ROWS.get(file_name, {}).get(sheet_name)
    if configured:
        return configured
    best_index = 1
    best_score = -1
    for index, row in enumerate(preview_rows[:12], start=1):
        headers = [clean_cell(value) for value in row]
        filled = [header for header in headers if header]
        score = len(filled)
        if any(keyword in " ".join(filled).lower() for keyword in ("cliente", "produto", "pedido", "data", "valor", "nota", "vendedor")):
            score += 10
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def row_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=json_default).encode("utf-8")).hexdigest()


def worksheet_rows(path: Path, *, drive_file_id: str, drive_file_name: str, sync_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    worksheets: list[dict[str, Any]] = []
    staging_rows: list[dict[str, Any]] = []
    sheet_names = [sheet.title for sheet in workbook.worksheets]
    detected = detect_type(drive_file_name, sheet_names)

    for worksheet in workbook.worksheets:
        preview_rows = list(worksheet.iter_rows(min_row=1, max_row=min(12, worksheet.max_row), values_only=True))
        header_row = infer_header_row(path.name, worksheet.title, preview_rows)
        header_values = next(worksheet.iter_rows(min_row=header_row, max_row=header_row, values_only=True), ())
        headers = [clean_cell(value) or f"coluna_{index + 1}" for index, value in enumerate(header_values)]
        rows_in_sheet = 0
        rows_insertable = 0

        for row_number, values in enumerate(worksheet.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
            if not values or not any(value not in (None, "") for value in values):
                continue
            rows_in_sheet += 1
            payload = {
                headers[index] if index < len(headers) else f"coluna_{index + 1}": clean_cell(value)
                for index, value in enumerate(values)
            }
            payload = {key: value for key, value in payload.items() if key and value != ""}
            if not payload:
                continue
            rows_insertable += 1
            staging_payload = {
                "drive_file_id": drive_file_id,
                "drive_file_name": drive_file_name,
                "sheet_name": worksheet.title,
                "row_number": row_number,
                "tipo_planilha": detected,
                "data": payload,
            }
            staging_rows.append(
                {
                    "source_system": "GOOGLE_DRIVE_ARCHIVE",
                    "source_id": f"{drive_file_id}:{worksheet.title}:{row_number}",
                    "entidade": f"planilha_{detected.lower()}",
                    "payload_original": staging_payload,
                    "dados_transformados": payload,
                    "sync_id": sync_id,
                    "hash_registro": row_hash(staging_payload),
                    "tabela_destino": None,
                }
            )
        worksheets.append(
            {
                "name": worksheet.title,
                "rows": worksheet.max_row,
                "cols": worksheet.max_column,
                "header_row": header_row,
                "rows_read": rows_in_sheet,
                "rows_insertable": rows_insertable,
                "headers": headers,
            }
        )
    workbook.close()
    return staging_rows, worksheets, detected


def csv_rows(path: Path, *, drive_file_id: str, drive_file_name: str, sync_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    import csv

    detected = detect_type(drive_file_name, [path.stem])
    staging_rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        headers = [clean_cell(header) for header in (reader.fieldnames or [])]
        for row_number, row in enumerate(reader, start=2):
            payload = {clean_cell(key): clean_cell(value) for key, value in row.items() if clean_cell(key) and clean_cell(value) != ""}
            if not payload:
                continue
            staging_payload = {
                "drive_file_id": drive_file_id,
                "drive_file_name": drive_file_name,
                "sheet_name": path.stem,
                "row_number": row_number,
                "tipo_planilha": detected,
                "data": payload,
            }
            staging_rows.append(
                {
                    "source_system": "GOOGLE_DRIVE_ARCHIVE",
                    "source_id": f"{drive_file_id}:{path.stem}:{row_number}",
                    "entidade": f"planilha_{detected.lower()}",
                    "payload_original": staging_payload,
                    "dados_transformados": payload,
                    "sync_id": sync_id,
                    "hash_registro": row_hash(staging_payload),
                    "tabela_destino": None,
                }
            )
    worksheets = [
        {
            "name": path.stem,
            "rows": len(staging_rows) + 1,
            "cols": len(headers),
            "header_row": 1,
            "rows_read": len(staging_rows),
            "rows_insertable": len(staging_rows),
            "headers": headers,
        }
    ]
    return staging_rows, worksheets, detected


def insert_staging_rows(cur: Any, rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for row in rows:
        cur.execute(
            """
            insert into public.staging_dados(
              source_system, source_id, entidade, payload_original, dados_transformados,
              sync_id, hash_registro, status_validacao, tabela_destino
            )
            select %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, 'valido', %s
            where not exists (
              select 1
              from public.staging_dados
              where source_system = %s
                and source_id = %s
                and hash_registro = %s
            )
            """,
            (
                row["source_system"],
                row["source_id"],
                row["entidade"],
                Json(row["payload_original"]),
                Json(row["dados_transformados"]),
                row["sync_id"],
                row["hash_registro"],
                row["tabela_destino"],
                row["source_system"],
                row["source_id"],
                row["hash_registro"],
            ),
        )
        inserted += int(cur.rowcount or 0)
    return inserted


def download_spreadsheet(token: str, file_info: dict[str, Any], target_dir: Path) -> Path:
    name = file_info.get("name") or file_info["id"]
    mime_type = file_info.get("mimeType")
    suffix = Path(name).suffix.lower()
    base_name = slug(Path(name).stem or file_info["id"])
    modified = (file_info.get("modifiedTime") or "sem_data").replace(":", "").replace("-", "")
    if mime_type == GOOGLE_SHEETS_MIME:
        destination = target_dir / f"{base_name}_{modified}.xlsx"
        export_drive_file(token, file_info["id"], destination, XLSX_MIME)
        return destination
    if suffix not in SUPPORTED_EXTENSIONS:
        destination = target_dir / f"{base_name}_{modified}.xlsx"
    else:
        destination = target_dir / f"{base_name}_{modified}{suffix}"
    download_drive_file(token, file_info["id"], destination)
    return destination


def collect_drive_spreadsheets(*, execute: bool = True, max_files: int | None = None, max_depth: int = DEFAULT_SCAN_DEPTH) -> dict[str, Any]:
    env = load_env()
    config = archive_config(env)
    if config.provider != "google_drive" or not config.drive_folder_id:
        return {"status": "skipped", "reason": "Archive Google Drive nao configurado."}
    token = drive_access_token(config)
    if not token:
        raise RuntimeError("Credencial Google OAuth/Service Account nao configurada para Drive.")

    sync_id = f"drive_spreadsheets_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    files = list_spreadsheets_recursive(token, config.drive_folder_id, max_depth=max_depth)
    files = sorted(files, key=lambda item: item.get("modifiedTime") or "", reverse=True)
    if max_files is not None:
        files = files[:max_files]

    target_dir = (ROOT / config.local_dir / "google_drive_archive" / "incoming_spreadsheets").resolve()
    processed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.fontes_dados(nome, tipo, classificacao, status, frequencia_sincronizacao, url, descricao)
                values ('Google Drive Archive', 'csv_upload', 'secundaria', 'ativa', 'diaria', %s, 'Pasta archive monitorada automaticamente para planilhas.')
                on conflict (nome) do update set
                  status = 'ativa',
                  frequencia_sincronizacao = 'diaria',
                  atualizado_em = now()
                """,
                (env.get("ARCHIVE_GOOGLE_DRIVE_FOLDER_URL") or config.drive_folder_id,),
            )
            for file_info in files:
                if already_processed(cur, file_info):
                    skipped.append({"file_id": file_info["id"], "name": file_info.get("name"), "reason": "unchanged"})
                    continue
                local_path: Path | None = None
                ingestion_id = start_ingestion(cur, file_info, sync_id)
                try:
                    local_path = download_spreadsheet(token, file_info, target_dir)
                    cur.execute(
                        "update public.drive_spreadsheet_ingestions set local_path = %s where id = %s::uuid",
                        (str(local_path.relative_to(ROOT)), ingestion_id),
                    )
                    if local_path.suffix.lower() == ".csv":
                        staging_rows, worksheets, detected = csv_rows(
                            local_path,
                            drive_file_id=file_info["id"],
                            drive_file_name=file_info.get("name") or file_info["id"],
                            sync_id=sync_id,
                        )
                    else:
                        staging_rows, worksheets, detected = worksheet_rows(
                            local_path,
                            drive_file_id=file_info["id"],
                            drive_file_name=file_info.get("name") or file_info["id"],
                            sync_id=sync_id,
                        )
                    inserted = insert_staging_rows(cur, staging_rows) if execute else 0
                    finish_ingestion(
                        cur,
                        ingestion_id,
                        status="sucesso",
                        rows_read=len(staging_rows),
                        rows_inserted=inserted,
                        worksheets=worksheets,
                        file_hash=file_sha256(local_path),
                        detected_type=detected,
                    )
                    processed.append(
                        {
                            "file_id": file_info["id"],
                            "name": file_info.get("name"),
                            "modified_time": file_info.get("modifiedTime"),
                            "detected_type": detected,
                            "rows_read": len(staging_rows),
                            "rows_inserted": inserted,
                            "local_path": str(local_path.relative_to(ROOT)),
                        }
                    )
                except Exception as exc:
                    message = f"{type(exc).__name__}: {str(exc)[:500]}"
                    finish_ingestion(cur, ingestion_id, status="erro", error_message=message)
                    errors.append({"file_id": file_info["id"], "name": file_info.get("name"), "error": message})
            cur.execute(
                """
                update public.fontes_dados
                set ultima_sincronizacao = now(),
                    total_registros = %s,
                    registros_erro = %s,
                    status = %s,
                    atualizado_em = now()
                where nome = 'Google Drive Archive'
                """,
                (
                    sum(item["rows_inserted"] for item in processed),
                    len(errors),
                    "erro" if errors and not processed else "ativa",
                ),
            )
        if execute:
            conn.commit()
        else:
            conn.rollback()

    return {
        "status": "sucesso" if not errors else "parcial",
        "sync_id": sync_id,
        "files_found": len(files),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitora a pasta Archive do Google Drive e ingere planilhas novas.")
    parser.add_argument("--dry-run", action="store_true", help="Baixa e le planilhas, mas nao insere linhas em staging_dados.")
    parser.add_argument("--max-files", type=int, default=None, help="Limita quantidade de arquivos para diagnostico.")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_SCAN_DEPTH, help="Profundidade maxima de subpastas no Drive.")
    args = parser.parse_args()

    result = collect_drive_spreadsheets(execute=not args.dry_run, max_files=args.max_files, max_depth=args.max_depth)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))
    if result.get("errors"):
        sys.exit(2)


if __name__ == "__main__":
    main()
