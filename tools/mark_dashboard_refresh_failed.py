from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


def mark_failed(job_id: str, message: str) -> None:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update public.dashboard_refresh_steps
                set status = 'failed',
                    finished_at = coalesce(finished_at, now()),
                    error = coalesce(error, %s),
                    updated_at = now()
                where job_id = %s::uuid
                  and status in ('queued', 'running')
                """,
                (message, job_id),
            )
            cur.execute(
                """
                update public.dashboard_refresh_runs
                set status = 'failed',
                    finished_at = coalesce(finished_at, now()),
                    message = %s,
                    updated_at = now()
                where job_id = %s::uuid
                  and status in ('queued', 'running')
                """,
                (message, job_id),
            )
            conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Marca um dashboard_refresh_runs travado como falho.")
    parser.add_argument("job_id")
    parser.add_argument("--message", default="Job interrompido manualmente apos timeout/hang.")
    args = parser.parse_args()
    mark_failed(args.job_id, args.message)
    print(f"marked_failed {args.job_id}")


if __name__ == "__main__":
    main()
