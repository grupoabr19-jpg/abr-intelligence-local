from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_migrations import MIGRATIONS_DIR, connect_crm_database, load_env


CRM_MIGRATIONS = (
    "20260918233630_central_dados_staging_catalog.sql",
    "20260924214500_dim_regiao_varejo.sql",
    "20260925133000_atendimento_kommo_raw_layer.sql",
    "20260925143000_atendimento_dimensions_facts.sql",
    "20260925162000_atendimento_aggregates_events.sql",
    "20260925163500_atendimento_refresh_aggregate_counters.sql",
    "20260925172000_atendimento_official_contract.sql",
)


def main() -> None:
    env = load_env()
    if not env.get("DATABASE_CRM_URL") and not env.get("DATABASE_CRM_URL_POOLER"):
        raise SystemExit("DATABASE_CRM_URL ou DATABASE_CRM_URL_POOLER nao encontrado no .env.")

    with connect_crm_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists public.abr_migrations_applied (
                  name text primary key,
                  applied_at timestamptz not null default now()
                )
                """
            )
            conn.commit()

            for migration_name in CRM_MIGRATIONS:
                migration = MIGRATIONS_DIR / migration_name
                if not migration.exists():
                    raise SystemExit(f"Migration nao encontrada: {migration_name}")
                cur.execute("select 1 from public.abr_migrations_applied where name = %s", (migration.name,))
                if cur.fetchone():
                    print(f"skip {migration.name}")
                    continue
                print(f"apply {migration.name}")
                cur.execute(migration.read_text(encoding="utf-8"))
                cur.execute("insert into public.abr_migrations_applied(name) values (%s)", (migration.name,))
                conn.commit()

    print("crm_migrations_ok")


if __name__ == "__main__":
    main()
