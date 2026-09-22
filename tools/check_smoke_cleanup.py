from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


def main() -> None:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.staging_dados where sync_id like %s", ("SMOKE-EDGE-%",))
            print(f"smoke_staging_remaining={cur.fetchone()[0]}")

            cur.execute(
                "select count(*) from public.historico_importacoes where sync_id like %s",
                ("SMOKE-EDGE-%",),
            )
            print(f"smoke_historico_remaining={cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
