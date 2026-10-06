from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_migrations import MIGRATIONS_DIR, connect_market_database, load_env


MARKET_MIGRATION_NAMES = (
    "20260924203000_market_external_sources.sql",
    "20260929190000_market_source_registry.sql",
    "20260929193000_market_raw_api_sources.sql",
    "20260929195000_market_comex_stat.sql",
    "20260929201000_market_steel_inda_raw.sql",
    "20260929203000_market_cni_raw.sql",
    "20260929205000_market_caged_pncp.sql",
    "20260929211000_market_aneel_solar.sql",
    "20260930103000_market_world_bank.sql",
    "20260930104500_market_obrasgov.sql",
    "20260930161000_market_indicator_quality.sql",
    "20260930174500_market_filters_and_decision_aggs.sql",
)


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    index = 0
    while index < len(sql):
        char = sql[index]
        current.append(char)
        if char == "'":
            if in_single_quote and index + 1 < len(sql) and sql[index + 1] == "'":
                current.append(sql[index + 1])
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        index += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def should_skip_for_neon(statement: str) -> bool:
    normalized = " ".join(statement.lower().split())
    return (
        normalized.startswith("alter table") and "enable row level security" in normalized
    ) or normalized.startswith(("drop policy", "create policy", "grant "))


def market_migration_files() -> list[Path]:
    files = [MIGRATIONS_DIR / name for name in MARKET_MIGRATION_NAMES]
    missing = [path.name for path in files if not path.exists()]
    if missing:
        raise SystemExit("Market migrations ausentes: " + ", ".join(missing))
    return files


def main() -> None:
    env = load_env()
    with connect_market_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists public.abr_market_migrations_applied (
                  name text primary key,
                  applied_at timestamptz not null default now()
                )
                """
            )
            conn.commit()

            for migration in market_migration_files():
                cur.execute(
                    "select 1 from public.abr_market_migrations_applied where name = %s",
                    (migration.name,),
                )
                if cur.fetchone():
                    print(f"skip {migration.name}")
                    continue

                print(f"apply {migration.name}")
                sql = migration.read_text(encoding="utf-8")
                for statement in split_sql_statements(sql):
                    if should_skip_for_neon(statement):
                        continue
                    cur.execute(statement)
                cur.execute(
                    "insert into public.abr_market_migrations_applied(name) values (%s)",
                    (migration.name,),
                )
                conn.commit()

    print("market_migrations_ok")


if __name__ == "__main__":
    main()
