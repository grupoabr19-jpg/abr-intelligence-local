from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, urlparse

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def load_env() -> dict[str, str]:
    values: dict[str, str] = dict(os.environ)
    env_path = ROOT / ".env"
    if not env_path.exists():
        return values

    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.setdefault(key.strip(), value.strip())
    return values


def pooler_candidates_from_direct_url(database_url: str) -> list[tuple[str, str]]:
    parsed = urlparse(database_url)
    if not parsed.hostname or not parsed.hostname.startswith("db.") or not parsed.password:
        return []

    project_ref = parsed.hostname.split(".")[1]
    password = quote(parsed.password, safe="")

    candidates: list[tuple[str, str]] = []
    for region in ("us-west-2", "sa-east-1", "us-east-1", "us-east-2", "us-west-1", "eu-west-1"):
        for port in (6543, 5432):
            pooler_url = (
                f"postgresql://postgres.{project_ref}:{password}"
                f"@aws-0-{region}.pooler.supabase.com:{port}/postgres?sslmode=require"
            )
            candidates.append((f"pooler region={region} port={port}", pooler_url))
    return candidates


def project_ref_from_url(value: str) -> str | None:
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if host.startswith("db."):
        return host.split(".")[1]
    if ".pooler.supabase.com" in host and parsed.username and parsed.username.startswith("postgres."):
        return parsed.username.split(".", 1)[1]
    return None


def connect_database(
    env: dict[str, str],
    *,
    database_url_key: str = "DATABASE_URL",
    database_url_pooler_key: str = "DATABASE_URL_POOLER",
) -> psycopg.Connection:
    if (
        database_url_key == "DATABASE_URL"
        and database_url_pooler_key == "DATABASE_URL_POOLER"
        and (
            env.get("DATABASE_CORE_URL_POOLER")
            or env.get("DATABASE_CORE_URL")
            or env.get("DATABASE_NEON_URL_POOLER")
            or env.get("DATABASE_NEON_URL")
        )
    ):
        if env.get("DATABASE_CORE_URL_POOLER") or env.get("DATABASE_CORE_URL"):
            database_url_key = "DATABASE_CORE_URL"
            database_url_pooler_key = "DATABASE_CORE_URL_POOLER"
        elif env.get("DATABASE_NEON_URL"):
            database_url_key = "DATABASE_NEON_URL"
            database_url_pooler_key = "__DATABASE_NEON_URL_POOLER_IGNORED_FOR_CORE__"
        else:
            database_url_key = "DATABASE_NEON_URL"
            database_url_pooler_key = "DATABASE_NEON_URL_POOLER"

    database_url = env.get(database_url_key, "")
    database_url_pooler = env.get(database_url_pooler_key, "")

    candidates: list[tuple[str, str]] = []
    if database_url_pooler:
        pooler_ref = project_ref_from_url(database_url_pooler)
        direct_ref = project_ref_from_url(database_url)
        if direct_ref and pooler_ref and direct_ref != pooler_ref:
            print(f"skip {database_url_pooler_key}: project-ref diferente do {database_url_key}")
        else:
            candidates.append((database_url_pooler_key, database_url_pooler))

    parsed = urlparse(database_url)
    host = parsed.hostname or ""
    if host:
        if ".pooler.supabase.com" in host:
            candidates.append((database_url_key, database_url))
        elif host.startswith("db.") and host.endswith(".supabase.co"):
            candidates.extend(pooler_candidates_from_direct_url(database_url))
        else:
            candidates.append((database_url_key, database_url))

    if not candidates:
        raise SystemExit(f"Configure {database_url_pooler_key} ou {database_url_key}.")

    for label, url in candidates:
        print(f"trying {label}")
        try:
            conn = psycopg.connect(url, connect_timeout=8)
            previous_autocommit = conn.autocommit
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("set default_transaction_read_only = off")
            conn.autocommit = previous_autocommit
            return conn
        except Exception as exc:
            print(f"failed {label}: {type(exc).__name__}: {str(exc)[:180]}")

    raise SystemExit("Nao foi possivel conectar ao Postgres configurado. Verifique host, usuario, senha e rede.")


def connect_core_database(env: dict[str, str]) -> psycopg.Connection:
    if env.get("DATABASE_CORE_URL_POOLER") or env.get("DATABASE_CORE_URL"):
        return connect_database(
            env,
            database_url_key="DATABASE_CORE_URL",
            database_url_pooler_key="DATABASE_CORE_URL_POOLER",
        )
    if env.get("DATABASE_NEON_URL"):
        return connect_database(
            env,
            database_url_key="DATABASE_NEON_URL",
            database_url_pooler_key="__DATABASE_NEON_URL_POOLER_IGNORED_FOR_CORE__",
        )
    if env.get("DATABASE_NEON_URL_POOLER"):
        return connect_database(
            env,
            database_url_key="DATABASE_NEON_URL",
            database_url_pooler_key="DATABASE_NEON_URL_POOLER",
        )
    return connect_database(env)


def connect_crm_database(env: dict[str, str]) -> psycopg.Connection:
    if env.get("DATABASE_CRM_URL_POOLER") or env.get("DATABASE_CRM_URL"):
        return connect_database(
            env,
            database_url_key="DATABASE_CRM_URL",
            database_url_pooler_key="DATABASE_CRM_URL_POOLER",
        )
    return connect_database(env)


def connect_market_database(env: dict[str, str]) -> psycopg.Connection:
    if env.get("DATABASE_MARKET_URL_POOLER") or env.get("DATABASE_MARKET_URL"):
        return connect_database(
            env,
            database_url_key="DATABASE_MARKET_URL",
            database_url_pooler_key="DATABASE_MARKET_URL_POOLER",
        )
    if env.get("DATABASE_NEON_URL_POOLER"):
        return connect_database(
            env,
            database_url_key="__DATABASE_NEON_URL_IGNORED_FOR_MARKET__",
            database_url_pooler_key="DATABASE_NEON_URL_POOLER",
        )
    if not (env.get("DATABASE_CORE_URL_POOLER") or env.get("DATABASE_CORE_URL") or env.get("DATABASE_NEON_URL")):
        if env.get("DATABASE_NEON_URL"):
            return connect_database(
                env,
                database_url_key="DATABASE_NEON_URL",
                database_url_pooler_key="__DATABASE_NEON_URL_POOLER_IGNORED_FOR_MARKET__",
            )
    raise SystemExit("Configure DATABASE_MARKET_URL_POOLER ou DATABASE_MARKET_URL para o banco de Mercado.")


def ensure_supabase_compatible_roles(cur: psycopg.Cursor) -> None:
    for role_name in ("anon", "authenticated", "service_role"):
        cur.execute("select 1 from pg_roles where rolname = %s", (role_name,))
        if cur.fetchone():
            continue
        cur.execute(f"create role {role_name} nologin")


def has_storage_buckets(cur: psycopg.Cursor) -> bool:
    cur.execute(
        """
        select 1
        from information_schema.tables
        where table_schema = 'storage'
          and table_name = 'buckets'
        """
    )
    return cur.fetchone() is not None


def has_public_function(cur: psycopg.Cursor, function_name: str) -> bool:
    cur.execute(
        """
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proname = %s
        limit 1
        """,
        (function_name,),
    )
    return cur.fetchone() is not None


def main() -> None:
    env = load_env()
    if not (
        env.get("DATABASE_CORE_URL")
        or env.get("DATABASE_CORE_URL_POOLER")
        or env.get("DATABASE_NEON_URL")
        or env.get("DATABASE_NEON_URL_POOLER")
        or env.get("DATABASE_URL")
        or env.get("DATABASE_URL_POOLER")
    ):
        raise SystemExit("DATABASE_NEON_URL ou DATABASE_CORE_URL nao encontrado no .env.")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise SystemExit("Nenhuma migration encontrada.")

    with connect_database(env) as conn:
        with conn.cursor() as cur:
            ensure_supabase_compatible_roles(cur)
            storage_buckets_available = has_storage_buckets(cur)
            rls_auto_enable_available = has_public_function(cur, "rls_auto_enable")
            cur.execute(
                """
                create table if not exists public.abr_migrations_applied (
                  name text primary key,
                  applied_at timestamptz not null default now()
                )
                """
            )
            conn.commit()

            for migration in migration_files:
                cur.execute("select 1 from public.abr_migrations_applied where name = %s", (migration.name,))
                if cur.fetchone():
                    print(f"skip {migration.name}")
                    continue

                print(f"apply {migration.name}")
                sql = migration.read_text(encoding="utf-8")
                if "storage.buckets" in sql and not storage_buckets_available:
                    print(f"skip {migration.name}: storage.buckets indisponivel neste Postgres")
                    cur.execute(
                        "insert into public.abr_migrations_applied(name) values (%s)",
                        (migration.name,),
                    )
                    conn.commit()
                    continue
                if "public.rls_auto_enable()" in sql and not rls_auto_enable_available:
                    print(f"skip {migration.name}: public.rls_auto_enable() indisponivel neste Postgres")
                    cur.execute(
                        "insert into public.abr_migrations_applied(name) values (%s)",
                        (migration.name,),
                    )
                    conn.commit()
                    continue
                cur.execute(sql)
                cur.execute(
                    "insert into public.abr_migrations_applied(name) values (%s)",
                    (migration.name,),
                )
                conn.commit()

    print("migrations_ok")


if __name__ == "__main__":
    main()
