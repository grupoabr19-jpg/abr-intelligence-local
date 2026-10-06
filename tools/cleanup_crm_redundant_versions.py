from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_crm_database, load_env


RAW_TABLES = (
    "raw_kommo_users",
    "raw_kommo_pipelines",
    "raw_kommo_statuses",
    "raw_kommo_leads",
    "raw_kommo_tasks",
    "raw_kommo_events",
    "raw_kommo_contacts",
    "raw_kommo_companies",
)


def table_exists(cur: Any, table_name: str) -> bool:
    cur.execute("select to_regclass(%s)", (f"public.{table_name}",))
    return cur.fetchone()[0] is not None


def count_targets(cur: Any) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    if table_exists(cur, "staging_dados"):
        cur.execute(
            """
            select
              count(*) filter(where entidade = 'atendimento_kommo' and ativo = true)::int,
              count(*) filter(where entidade = 'atendimento_kommo' and ativo = false)::int,
              count(*) filter(where entidade = 'atendimento_kommo')::int
            from public.staging_dados
            """
        )
        active, inactive, total = cur.fetchone()
        result["staging_dados:atendimento_kommo"] = {
            "active": active,
            "inactive": inactive,
            "total": total,
        }
    for table_name in RAW_TABLES:
        if not table_exists(cur, table_name):
            continue
        cur.execute(
            f"""
            select
              count(*) filter(where ativo = true)::int,
              count(*) filter(where ativo = false)::int,
              count(*)::int
            from public.{table_name}
            """
        )
        active, inactive, total = cur.fetchone()
        result[table_name] = {"active": active, "inactive": inactive, "total": total}
    return result


def delete_inactive(cur: Any) -> dict[str, int]:
    deleted: dict[str, int] = {}
    if table_exists(cur, "staging_dados"):
        cur.execute(
            """
            delete from public.staging_dados
            where entidade = 'atendimento_kommo'
              and ativo = false
            """
        )
        deleted["staging_dados:atendimento_kommo"] = int(cur.rowcount or 0)
    for table_name in RAW_TABLES:
        if not table_exists(cur, table_name):
            continue
        cur.execute(f"delete from public.{table_name} where ativo = false")
        deleted[table_name] = int(cur.rowcount or 0)
    return deleted


def table_sizes(cur: Any) -> list[dict[str, Any]]:
    names = ["staging_dados", *RAW_TABLES]
    cur.execute(
        """
        select
          c.relname,
          pg_size_pretty(pg_total_relation_size(c.oid)),
          pg_total_relation_size(c.oid)::bigint
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relname = any(%s)
        order by pg_total_relation_size(c.oid) desc
        """,
        (names,),
    )
    return [{"table": row[0], "size": row[1], "bytes": int(row[2])} for row in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove versoes inativas/duplicadas do CRM sem apagar registros atuais.")
    parser.add_argument("--execute", action="store_true", help="Executa deletes. Sem isto, apenas diagnostica.")
    parser.add_argument("--vacuum", action="store_true", help="Executa VACUUM ANALYZE apos delete. Nao faz VACUUM FULL.")
    args = parser.parse_args()

    env = load_env()
    with connect_crm_database(env) as conn:
        with conn.cursor() as cur:
            before = count_targets(cur)
            before_sizes = table_sizes(cur)
            deleted: dict[str, int] = {}
            if args.execute:
                deleted = delete_inactive(cur)
                conn.commit()
                if args.vacuum:
                    conn.autocommit = True
                    for table_name in ("staging_dados", *RAW_TABLES):
                        if table_exists(cur, table_name):
                            cur.execute(f"vacuum analyze public.{table_name}")
                    conn.autocommit = False
            else:
                conn.rollback()
            after = count_targets(cur)
            after_sizes = table_sizes(cur)
    print(
        json.dumps(
            {
                "executed": args.execute,
                "vacuum": args.vacuum,
                "before": before,
                "deleted": deleted,
                "after": after,
                "before_sizes": before_sizes,
                "after_sizes": after_sizes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
