from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
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


def connect_database(env: dict[str, str]) -> psycopg.Connection:
    database_url = env.get("DATABASE_URL", "")
    database_url_pooler = env.get("DATABASE_URL_POOLER", "")

    candidates: list[tuple[str, str]] = []
    if database_url_pooler:
        pooler_ref = project_ref_from_url(database_url_pooler)
        direct_ref = project_ref_from_url(database_url)
        if direct_ref and pooler_ref and direct_ref != pooler_ref:
            print("skip DATABASE_URL_POOLER: project-ref diferente do DATABASE_URL")
        else:
            candidates.append(("DATABASE_URL_POOLER", database_url_pooler))

    parsed = urlparse(database_url)
    if parsed.hostname and ".pooler.supabase.com" in parsed.hostname:
        candidates.append(("DATABASE_URL", database_url))
    else:
        candidates.extend(pooler_candidates_from_direct_url(database_url))

    if not candidates:
        raise SystemExit("Configure DATABASE_URL_POOLER ou use DATABASE_URL do Supabase com senha para montar o pooler IPv4.")

    for label, url in candidates:
        print(f"trying {label}")
        try:
            return psycopg.connect(url, connect_timeout=8)
        except Exception as exc:
            print(f"failed {label}: {type(exc).__name__}: {str(exc)[:180]}")

    raise SystemExit("Nao foi possivel conectar pelo pooler IPv4. Verifique senha, project-ref e regiao do pooler.")


def main() -> None:
    env = load_env()
    if not env.get("DATABASE_URL") and not env.get("DATABASE_URL_POOLER"):
        raise SystemExit("DATABASE_URL ou DATABASE_URL_POOLER nao encontrado no .env.")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise SystemExit("Nenhuma migration encontrada.")

    with connect_database(env) as conn:
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

            for migration in migration_files:
                cur.execute("select 1 from public.abr_migrations_applied where name = %s", (migration.name,))
                if cur.fetchone():
                    print(f"skip {migration.name}")
                    continue

                print(f"apply {migration.name}")
                sql = migration.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute(
                    "insert into public.abr_migrations_applied(name) values (%s)",
                    (migration.name,),
                )
                conn.commit()

    print("migrations_ok")


if __name__ == "__main__":
    main()
