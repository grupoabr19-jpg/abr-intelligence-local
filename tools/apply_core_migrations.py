from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_market_migrations import split_sql_statements
from tools.apply_migrations import MIGRATIONS_DIR, connect_core_database, load_env


CORE_MIGRATION_NAMES = (
    "20260918233630_central_dados_staging_catalog.sql",
    "20260921200000_persistir_aba_xlsx.sql",
    "20260921203000_aster_staging_idempotencia.sql",
    "20260921204500_aster_capture_metadata.sql",
    "20260924173000_dashboard_sales_summary_cache.sql",
    "20260924214500_dim_regiao_varejo.sql",
    "20260928143000_data_archive_catalog.sql",
    "20260928193000_dashboard_sales_fact.sql",
    "20260929123000_dashboard_refresh_runs.sql",
    "20260930143000_drive_spreadsheet_ingestions.sql",
    "20261001141000_drive_spreadsheet_dashboard_cache.sql",
    "20261002103000_business_channel_dimensions.sql",
)


def core_migration_files() -> list[Path]:
    files = [MIGRATIONS_DIR / name for name in CORE_MIGRATION_NAMES]
    missing = [path.name for path in files if not path.exists()]
    if missing:
        raise SystemExit("Core migrations ausentes: " + ", ".join(missing))
    return files


def sanitize_for_neon(sql: str) -> str:
    sql = re.sub(r"\bREFERENCES\s+auth\.users\s*\(\s*id\s*\)\s+ON\s+DELETE\s+SET\s+NULL", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bREFERENCES\s+auth\.users\s*\(\s*id\s*\)", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"do\s+\$\$.*?end\s+\$\$;", "", sql, flags=re.IGNORECASE | re.DOTALL)
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def should_skip_for_neon(statement: str) -> bool:
    normalized = " ".join(statement.lower().split())
    return (
        normalized.startswith("alter table") and "enable row level security" in normalized
    ) or normalized.startswith(("drop policy", "create policy", "grant "))


def main() -> None:
    env = load_env()
    with connect_core_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists public.abr_core_migrations_applied (
                  name text primary key,
                  applied_at timestamptz not null default now()
                )
                """
            )
            conn.commit()

            for migration in core_migration_files():
                cur.execute(
                    "select 1 from public.abr_core_migrations_applied where name = %s",
                    (migration.name,),
                )
                if cur.fetchone():
                    print(f"skip {migration.name}")
                    continue

                print(f"apply {migration.name}")
                sql = sanitize_for_neon(migration.read_text(encoding="utf-8"))
                for statement in split_sql_statements(sql):
                    if should_skip_for_neon(statement):
                        continue
                    cur.execute(statement)
                cur.execute(
                    "insert into public.abr_core_migrations_applied(name) values (%s)",
                    (migration.name,),
                )
                conn.commit()

    print("core_migrations_ok")


if __name__ == "__main__":
    main()
