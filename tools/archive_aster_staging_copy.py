from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.archive_storage import (
    archive_config,
    drive_access_token,
    ensure_drive_folder,
    file_sha256,
    json_default,
    register_archive_catalog,
    upload_drive_file,
)
from tools.apply_migrations import connect_database, load_env


HEX_BUCKETS = tuple("0123456789abcdef")


def drive_parent_for(token: str | None, root_folder_id: str, relative_dir: Path) -> str | None:
    if not token or not root_folder_id:
        return None
    parent_id = root_folder_id
    for folder_name in relative_dir.parts:
        parent_id = ensure_drive_folder(token, parent_id, folder_name)
    return parent_id


def list_entities(conn: Any, only_entities: set[str] | None = None) -> list[dict[str, Any]]:
    where = "entidade like 'aster_report_%%'"
    params: list[Any] = []
    if only_entities:
        where += " and entidade = any(%s)"
        params.append(sorted(only_entities))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select entidade, count(*)::int
            from public.staging_dados
            where {where}
            group by entidade
            order by count(*) desc
            """,
            params,
        )
        return [{"entity": row[0], "rows": row[1]} for row in cur.fetchall()]


def chunk_count(conn: Any, entity: str, bucket: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(*)::int
            from public.staging_dados
            where entidade = %s and left(replace(id::text, '-', ''), 1) = %s
            """,
            (entity, bucket),
        )
        return int(cur.fetchone()[0] or 0)


def copy_query(conn: Any, *, entity: str, path: Path, bucket: str | None = None) -> int:
    if bucket is None:
        where_sql = sql.SQL("entidade = {entity}").format(entity=sql.Literal(entity))
    else:
        where_sql = sql.SQL("entidade = {entity} and left(replace(id::text, '-', ''), 1) = {bucket}").format(
            entity=sql.Literal(entity),
            bucket=sql.Literal(bucket),
        )
    query = sql.SQL(
        """
        copy (
          select
            id,
            fonte_id,
            source_system,
            source_id,
            entidade,
            payload_original::text as payload_original,
            dados_transformados::text as dados_transformados,
            imported_at,
            updated_at,
            sync_id,
            hash_registro,
            status_validacao,
            erro_validacao,
            tabela_destino,
            registro_destino_id,
            ativo,
            coleta_metadata::text as coleta_metadata
          from public.staging_dados
          where {where_sql}
        ) to stdout with csv header
        """
    ).format(where_sql=where_sql)

    line_count = 0
    with conn.cursor() as cur, gzip.open(path, "wb", compresslevel=6) as file_obj:
        with cur.copy(query) as copy:
            for data in copy:
                chunk = bytes(data)
                line_count += chunk.count(b"\n")
                file_obj.write(chunk)
    rows = max(0, line_count - 1)
    if rows == 0:
        path.unlink(missing_ok=True)
    return rows


def archive_entities(entities: list[dict[str, Any]], *, env: dict[str, str], token: str | None) -> list[dict[str, Any]]:
    config = archive_config(env)
    now = datetime.now(timezone.utc)
    sync_id = f"core_aster_copy_{now.strftime('%Y%m%d%H%M%S')}"
    archived: list[dict[str, Any]] = []

    with connect_database(env) as conn:
        for item in entities:
            entity = item["entity"]
            relative_dir = (
                Path("supabase_core")
                / "legacy_aster_staging"
                / entity
                / now.strftime("%Y")
                / now.strftime("%m")
                / now.strftime("%d")
            )
            archive_dir = (ROOT / config.local_dir / relative_dir).resolve()
            archive_dir.mkdir(parents=True, exist_ok=True)
            base_name = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{entity}_{sync_id}"
            files: list[dict[str, Any]] = []
            row_count = 0

            data_path = archive_dir / f"{base_name}.csv.gz"
            rows = copy_query(conn, entity=entity, path=data_path)
            if rows:
                row_count += rows
                files.append(
                    {
                        "format": "csv.gz",
                        "path": str(data_path),
                        "relative_path": str(data_path.relative_to(ROOT)),
                        "bytes": data_path.stat().st_size,
                        "sha256": file_sha256(data_path),
                        "rows": rows,
                        "drive": None,
                    }
                )

            manifest = {
                "source_system": "SUPABASE_CORE",
                "entity": entity,
                "sync_id": sync_id,
                "row_count": row_count,
                "archived_at": now.isoformat(),
                "metadata": {
                    "reason": "prune_supabase_core_staging",
                    "format": "copy_csv_gzip",
                },
                "files": files,
            }
            manifest_path = archive_dir / f"{base_name}_manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
            files.append(
                {
                    "format": "manifest",
                    "path": str(manifest_path),
                    "relative_path": str(manifest_path.relative_to(ROOT)),
                    "bytes": manifest_path.stat().st_size,
                    "sha256": file_sha256(manifest_path),
                    "drive": None,
                }
            )

            drive_error = None
            if config.provider == "google_drive" and config.drive_folder_id:
                try:
                    parent_id = drive_parent_for(token, config.drive_folder_id, relative_dir)
                    if not parent_id:
                        raise RuntimeError("Credencial Google nao configurada.")
                    for file_info in files:
                        file_info["drive"] = upload_drive_file(token or "", parent_id, Path(file_info["path"]))
                except Exception as exc:
                    drive_error = f"{type(exc).__name__}: {str(exc)[:300]}"

            result = {
                "source_system": "SUPABASE_CORE",
                "entity": entity,
                "sync_id": sync_id,
                "row_count": row_count,
                "archive_dir": str(archive_dir),
                "relative_dir": str(relative_dir),
                "files": files,
                "drive_error": drive_error,
            }
            register_archive_catalog(
                result,
                metadata={
                    "reason": "prune_supabase_core_staging",
                    "format": "copy_csv_gzip",
                    "drive_error": drive_error,
                },
                env=env,
            )
            archived.append(
                {
                    "entity": entity,
                    "rows": row_count,
                    "files": len(files),
                    "bytes": sum(int(file_info["bytes"]) for file_info in files),
                    "drive_error": drive_error,
                }
            )
    return archived


def main() -> None:
    parser = argparse.ArgumentParser(description="Arquiva staging Aster via COPY CSV gzip por buckets de UUID.")
    parser.add_argument("--entity", action="append", help="Arquiva apenas uma entidade especifica. Pode repetir.")
    args = parser.parse_args()

    env = load_env()
    only_entities = set(args.entity or []) or None
    config = archive_config(env)
    token = drive_access_token(config) if config.provider == "google_drive" else None

    with connect_database(env) as conn:
        entities = list_entities(conn, only_entities)

    archived = archive_entities(entities, env=env, token=token)
    drive_errors = [item for item in archived if item.get("drive_error")]
    print(json.dumps({"archived": archived, "drive_errors": drive_errors}, ensure_ascii=False, indent=2, default=str))
    if drive_errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
