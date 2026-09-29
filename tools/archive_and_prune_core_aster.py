from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def drive_parent_for(token: str | None, root_folder_id: str, relative_dir: Path) -> str | None:
    if not token or not root_folder_id:
        return None
    parent_id = root_folder_id
    for folder_name in relative_dir.parts:
        parent_id = ensure_drive_folder(token, parent_id, folder_name)
    return parent_id


def list_aster_entities(conn: Any, only_entities: set[str] | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        params: list[Any] = []
        where_sql = "entidade like 'aster_report_%%'"
        if only_entities:
            where_sql += " and entidade = any(%s)"
            params.append(sorted(only_entities))
        cur.execute(
            f"""
            select entidade, count(*)::int as rows
            from public.staging_dados
            where {where_sql}
            group by entidade
            order by rows desc
            """,
            params,
        )
        return [{"entity": row[0], "rows": row[1]} for row in cur.fetchall()]


def archive_entity(
    conn: Any,
    *,
    entity: str,
    sync_id: str,
    env: dict[str, str],
    token: str | None,
    chunk_size: int,
) -> dict[str, Any]:
    config = archive_config(env)
    now = datetime.now(timezone.utc)
    relative_dir = Path("supabase_core") / "legacy_aster_staging" / entity / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    archive_dir = (ROOT / config.local_dir / relative_dir).resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{entity}_{sync_id}"

    row_count = 0
    last_id: str | None = None
    chunk_index = 0
    chunk_rows = 0
    chunk_file = None
    chunk_path: Path | None = None
    files: list[dict[str, Any]] = []

    def open_chunk() -> Any:
        nonlocal chunk_index, chunk_rows, chunk_path
        chunk_index += 1
        chunk_rows = 0
        chunk_path = archive_dir / f"{base_name}_part{chunk_index:04d}.jsonl"
        return chunk_path.open("w", encoding="utf-8", newline="\n")

    def close_chunk() -> None:
        nonlocal chunk_file, chunk_path
        if not chunk_file or not chunk_path:
            return
        chunk_file.close()
        if chunk_rows == 0:
            chunk_path.unlink(missing_ok=True)
        else:
            files.append(
                {
                    "format": "jsonl",
                    "path": str(chunk_path),
                    "relative_path": str(chunk_path.relative_to(ROOT)),
                    "bytes": chunk_path.stat().st_size,
                    "sha256": file_sha256(chunk_path),
                    "rows": chunk_rows,
                    "drive": None,
                }
            )
        chunk_file = None
        chunk_path = None

    try:
        chunk_file = open_chunk()
        while True:
            if last_id:
                sql = """
                    select id, to_jsonb(t)
                    from (
                      select *
                      from public.staging_dados
                      where entidade = %s and id > %s::uuid
                      order by id
                      limit 1000
                    ) t
                """
                params = (entity, last_id)
            else:
                sql = """
                    select id, to_jsonb(t)
                    from (
                      select *
                      from public.staging_dados
                      where entidade = %s
                      order by id
                      limit 1000
                    ) t
                """
                params = (entity,)
            with conn.cursor() as cur:
                cur.execute(sql, params)
                batch = cur.fetchall()
            if not batch:
                break
            for row_id, payload in batch:
                if chunk_rows >= chunk_size:
                    close_chunk()
                    chunk_file = open_chunk()
                last_id = str(row_id)
                chunk_file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=json_default))
                chunk_file.write("\n")
                chunk_rows += 1
            row_count += len(batch)
    finally:
        close_chunk()

    if row_count == 0:
        return {"entity": entity, "rows": 0, "archived": False}

    manifest = {
        "source_system": "SUPABASE_CORE",
        "entity": entity,
        "sync_id": sync_id,
        "row_count": row_count,
        "archived_at": now.isoformat(),
        "metadata": {
            "reason": "compact_dashboard_sales_fact_created",
            "format": "chunked_streamed_jsonl",
            "chunk_size": chunk_size,
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
            "reason": "compact_dashboard_sales_fact_created",
            "format": "chunked_streamed_jsonl",
            "chunk_size": chunk_size,
            "drive_error": drive_error,
        },
        env=env,
    )
    return {"entity": entity, "rows": row_count, "archived": True, "drive_error": drive_error, "files": len(files)}


def prune_aster_staging(conn: Any, *, vacuum_full: bool, only_entities: set[str] | None = None) -> int:
    with conn.cursor() as cur:
        if only_entities:
            cur.execute("delete from public.staging_dados where entidade = any(%s)", (sorted(only_entities),))
        else:
            cur.execute("delete from public.staging_dados where entidade like 'aster_report_%'")
        deleted = cur.rowcount
    conn.commit()
    if vacuum_full:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("vacuum full public.staging_dados")
            cur.execute("analyze public.staging_dados")
        conn.autocommit = False
    return int(deleted or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Arquiva e remove staging bruto do Aster no Supabase core.")
    parser.add_argument("--execute", action="store_true", help="Remove linhas aster_report_* depois do archive.")
    parser.add_argument("--skip-archive", action="store_true", help="Pula archive e executa apenas limpeza.")
    parser.add_argument("--allow-drive-error", action="store_true", help="Permite limpeza mesmo se upload ao Drive falhar.")
    parser.add_argument("--vacuum-full", action="store_true", help="Executa VACUUM FULL para reduzir fisicamente staging_dados.")
    parser.add_argument("--entity", action="append", help="Arquiva/remove apenas uma entidade especifica. Pode repetir.")
    parser.add_argument("--chunk-size", type=int, default=25000, help="Linhas por arquivo JSONL no archive.")
    args = parser.parse_args()

    env = load_env()
    sync_id = f"core_aster_prune_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    config = archive_config(env)
    token = drive_access_token(config) if config.provider == "google_drive" else None
    only_entities = set(args.entity or []) or None

    with connect_database(env) as conn:
        before = list_aster_entities(conn, only_entities)

    archived: list[dict[str, Any]] = []
    if not args.skip_archive:
        with connect_database(env) as conn:
            for item in before:
                archived.append(
                    archive_entity(
                        conn,
                        entity=item["entity"],
                        sync_id=sync_id,
                        env=env,
                        token=token,
                        chunk_size=max(1, args.chunk_size),
                    )
                )
            conn.rollback()
        drive_errors = [item for item in archived if item.get("drive_error")]
        if drive_errors and not args.allow_drive_error:
            raise SystemExit(json.dumps({"status": "aborted_drive_error", "errors": drive_errors}, ensure_ascii=False, indent=2))

    deleted = 0
    if args.execute:
        with connect_database(env) as conn:
            deleted = prune_aster_staging(conn, vacuum_full=args.vacuum_full, only_entities=only_entities)

    with connect_database(env) as conn:
        after = list_aster_entities(conn, only_entities)
        with conn.cursor() as cur:
            cur.execute("select pg_size_pretty(pg_total_relation_size('public.staging_dados'::regclass))")
            staging_size = cur.fetchone()[0]
            cur.execute("select pg_size_pretty(pg_database_size(current_database()))")
            database_size = cur.fetchone()[0]

    print(
        json.dumps(
            {
                "sync_id": sync_id,
                "executed": args.execute,
                "vacuum_full": args.vacuum_full,
                "deleted": deleted,
                "before": before,
                "after": after,
                "staging_size": staging_size,
                "database_size": database_size,
                "archived": archived,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
