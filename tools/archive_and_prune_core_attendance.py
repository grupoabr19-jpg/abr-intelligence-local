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
    access_token_from_service_account,
    archive_config,
    ensure_drive_folder,
    file_sha256,
    json_default,
    register_archive_catalog,
    upload_drive_file,
)
from tools.apply_migrations import connect_database, load_env


FULL_TABLES = (
    "raw_kommo_users",
    "raw_kommo_pipelines",
    "raw_kommo_statuses",
    "raw_kommo_leads",
    "raw_kommo_tasks",
    "raw_kommo_events",
    "raw_kommo_contacts",
    "raw_kommo_companies",
    "atendimento_evento_resposta",
    "atendimento_agregado_diario",
    "atendimento_agregado_colaborador",
    "atendimento_agregado_regiao",
    "fato_atendimento_followup",
    "fato_atendimento_sla",
    "fato_atendimento_lead",
    "fact_kommo_interacoes",
    "fact_kommo_tasks",
    "fact_kommo_leads",
)


def table_exists(cur: Any, table_name: str) -> bool:
    cur.execute("select to_regclass(%s)", (f"public.{table_name}",))
    return cur.fetchone()[0] is not None


def count_rows(cur: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in FULL_TABLES:
        if table_exists(cur, table_name):
            cur.execute(f"select count(*) from public.{table_name}")
            counts[table_name] = int(cur.fetchone()[0])
    if table_exists(cur, "staging_dados"):
        cur.execute("select count(*) from public.staging_dados where entidade = %s", ("atendimento_kommo",))
        counts["staging_dados:atendimento_kommo"] = int(cur.fetchone()[0])
    return counts


def count_rows_with_connection(conn: Any) -> dict[str, int]:
    with conn.cursor() as cur:
        return count_rows(cur)


def drive_parent_for(token: str | None, root_folder_id: str, relative_dir: Path) -> str | None:
    if not token or not root_folder_id:
        return None
    parent_id = root_folder_id
    for folder_name in relative_dir.parts:
        parent_id = ensure_drive_folder(token, parent_id, folder_name)
    return parent_id


def archive_query_jsonl(
    conn: Any,
    *,
    name: str,
    sql: str,
    params: tuple[Any, ...],
    sync_id: str,
    env: dict[str, str],
    token: str | None,
) -> dict[str, Any]:
    config = archive_config(env)
    now = datetime.now(timezone.utc)
    relative_dir = Path("supabase_core") / "legacy_attendance" / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    archive_dir = (ROOT / config.local_dir / relative_dir).resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{name}_{sync_id}"
    jsonl_path = archive_dir / f"{base_name}.jsonl"

    row_count = 0
    with conn.cursor(name=f"archive_{name[:20]}") as stream:
        stream.itersize = 1000
        stream.execute(sql, params)
        with jsonl_path.open("w", encoding="utf-8", newline="\n") as file_obj:
            while True:
                batch = stream.fetchmany(1000)
                if not batch:
                    break
                for row in batch:
                    file_obj.write(json.dumps(row[0], ensure_ascii=False, sort_keys=True, default=json_default))
                    file_obj.write("\n")
                row_count += len(batch)

    if row_count == 0:
        jsonl_path.unlink(missing_ok=True)
        return {"entity": name, "rows": 0, "archived": False}

    files = [
        {
            "format": "jsonl",
            "path": str(jsonl_path),
            "relative_path": str(jsonl_path.relative_to(ROOT)),
            "bytes": jsonl_path.stat().st_size,
            "sha256": file_sha256(jsonl_path),
            "drive": None,
        }
    ]
    manifest = {
        "source_system": "SUPABASE_CORE",
        "entity": name,
        "sync_id": sync_id,
        "row_count": row_count,
        "archived_at": now.isoformat(),
        "metadata": {"reason": "migrated_attendance_to_crm_database", "format": "streamed_jsonl"},
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
        "entity": name,
        "sync_id": sync_id,
        "row_count": row_count,
        "archive_dir": str(archive_dir),
        "relative_dir": str(relative_dir),
        "files": files,
        "drive_error": drive_error,
    }
    register_archive_catalog(
        result,
        metadata={"reason": "migrated_attendance_to_crm_database", "format": "streamed_jsonl", "drive_error": drive_error},
        env=env,
    )
    return {"entity": name, "rows": row_count, "archived": True, "drive_error": drive_error, "files": len(files)}


def archive_all(conn: Any, env: dict[str, str], sync_id: str) -> list[dict[str, Any]]:
    config = archive_config(env)
    token = access_token_from_service_account(config) if config.provider == "google_drive" else None
    archived: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        if table_exists(cur, "staging_dados"):
            archived.append(
                archive_query_jsonl(
                    conn,
                    name="legacy_staging_dados_atendimento_kommo",
                    sql="""
                        select to_jsonb(t)
                        from (
                          select *
                          from public.staging_dados
                          where entidade = %s
                          order by imported_at nulls last, id
                        ) t
                    """,
                    params=("atendimento_kommo",),
                    sync_id=sync_id,
                    env=env,
                    token=token,
                )
            )
        for table_name in FULL_TABLES:
            if not table_exists(cur, table_name):
                continue
            archived.append(
                archive_query_jsonl(
                    conn,
                    name=f"legacy_{table_name}",
                    sql=f"select to_jsonb(t) from (select * from public.{table_name}) t",
                    params=(),
                    sync_id=sync_id,
                    env=env,
                    token=token,
                )
            )
    return archived


def prune(cur: Any) -> None:
    existing_tables = [table_name for table_name in FULL_TABLES if table_exists(cur, table_name)]
    if existing_tables:
        table_sql = ", ".join(f"public.{table_name}" for table_name in existing_tables)
        cur.execute(f"truncate table {table_sql} cascade")
    if table_exists(cur, "staging_dados"):
        cur.execute("delete from public.staging_dados where entidade = %s", ("atendimento_kommo",))


def main() -> None:
    parser = argparse.ArgumentParser(description="Arquiva e remove copias antigas de atendimento/Kommo do banco core.")
    parser.add_argument("--execute", action="store_true", help="Executa a limpeza depois do arquivo.")
    parser.add_argument("--allow-drive-error", action="store_true", help="Permite limpeza mesmo se upload ao Drive falhar.")
    args = parser.parse_args()

    env = load_env()
    sync_id = f"core_attendance_prune_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    with connect_database(env) as conn:
        before = count_rows_with_connection(conn)
        archived = archive_all(conn, env, sync_id)
        drive_errors = [item for item in archived if item.get("drive_error")]
        if drive_errors and not args.allow_drive_error:
            raise SystemExit(json.dumps({"status": "aborted_drive_error", "errors": drive_errors}, ensure_ascii=False, indent=2))

        if args.execute:
            with conn.cursor() as cur:
                prune(cur)
            conn.commit()
        else:
            conn.rollback()

        after = count_rows_with_connection(conn)

    print(
        json.dumps(
            {
                "sync_id": sync_id,
                "executed": args.execute,
                "before": before,
                "after": after,
                "archived": archived,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
