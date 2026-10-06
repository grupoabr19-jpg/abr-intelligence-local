from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_crm_database, connect_database, connect_market_database, load_env


def inspect(label: str, connector: Callable[[dict[str, str]], Any], env: dict[str, str]) -> dict[str, Any]:
    try:
        with connector(env) as conn:
            with conn.cursor() as cur:
                cur.execute("select pg_size_pretty(pg_database_size(current_database()))")
                database_size = cur.fetchone()[0]
                cur.execute(
                    """
                    select
                      c.relname,
                      pg_size_pretty(pg_total_relation_size(c.oid)) as pretty_size,
                      pg_total_relation_size(c.oid) as bytes
                    from pg_class c
                    join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'public'
                      and c.relkind in ('r', 'm')
                    order by bytes desc
                    limit 30
                    """
                )
                tables = [
                    {"table": row[0], "size": row[1], "bytes": int(row[2])}
                    for row in cur.fetchall()
                ]
                return {"database": label, "ok": True, "database_size": database_size, "tables": tables}
    except BaseException as exc:
        return {"database": label, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def main() -> None:
    env = load_env()
    results = [
        inspect("supabase1_core", connect_database, env),
        inspect("supabase2_crm", connect_crm_database, env),
        inspect("neon_market", connect_market_database, env),
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
