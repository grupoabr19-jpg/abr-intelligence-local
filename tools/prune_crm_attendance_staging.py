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


def stats(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        select
          count(*) filter(where entidade = 'atendimento_kommo')::int,
          count(*) filter(where entidade = 'atendimento_kommo' and ativo = true)::int,
          count(*) filter(where entidade = 'atendimento_kommo' and ativo = false)::int
        from public.staging_dados
        """
    )
    total, active, inactive = cur.fetchone()
    cur.execute(
        """
        select
          pg_size_pretty(pg_total_relation_size('public.staging_dados'::regclass)),
          pg_total_relation_size('public.staging_dados'::regclass)::bigint
        """
    )
    pretty_size, bytes_size = cur.fetchone()
    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "staging_size": pretty_size,
        "staging_bytes": int(bytes_size),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove staging_dados de atendimento apos refresh passar a usar raw_kommo.")
    parser.add_argument("--execute", action="store_true", help="Executa a limpeza.")
    parser.add_argument("--vacuum", action="store_true", help="Executa VACUUM ANALYZE public.staging_dados apos delete.")
    args = parser.parse_args()

    env = load_env()
    with connect_crm_database(env) as conn:
        with conn.cursor() as cur:
            before = stats(cur)
            deleted = 0
            if args.execute:
                cur.execute("delete from public.staging_dados where entidade = 'atendimento_kommo'")
                deleted = int(cur.rowcount or 0)
                conn.commit()
                if args.vacuum:
                    conn.autocommit = True
                    cur.execute("vacuum analyze public.staging_dados")
                    conn.autocommit = False
            else:
                conn.rollback()
            after = stats(cur)
    print(json.dumps({"executed": args.execute, "vacuum": args.vacuum, "before": before, "deleted": deleted, "after": after}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
