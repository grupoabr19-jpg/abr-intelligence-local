from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

import psycopg


ROOT = Path(__file__).resolve().parents[1]


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
    parsed_db_url = urlparse(database_url)
    if not parsed_db_url.hostname or not parsed_db_url.hostname.startswith("db.") or not parsed_db_url.password:
        return []

    project_ref = parsed_db_url.hostname.split(".")[1]
    password = quote(parsed_db_url.password, safe="")
    candidates: list[tuple[str, str]] = []
    for region in (
        "us-west-2",
        "sa-east-1",
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "eu-west-1",
        "eu-west-2",
        "eu-central-1",
    ):
        for port in (6543, 5432):
            pooler_url = (
                f"postgresql://postgres.{project_ref}:{password}"
                f"@aws-0-{region}.pooler.supabase.com:{port}/postgres?sslmode=require"
            )
            candidates.append((f"DATABASE_URL_POOLER region={region} port={port}", pooler_url))
    return candidates


def main() -> None:
    env = load_env()
    url = env.get("VITE_SUPABASE_URL") or env.get("NEXT_PUBLIC_SUPABASE_URL")
    database_url = env.get("DATABASE_URL")
    database_url_pooler = env.get("DATABASE_URL_POOLER")
    password = env.get("SUPABASE_PASSWORD")
    if not url:
        raise SystemExit("Missing VITE_SUPABASE_URL/NEXT_PUBLIC_SUPABASE_URL.")

    candidates: list[tuple[str, str]] = []
    if database_url_pooler:
        candidates.append(("DATABASE_URL_POOLER", database_url_pooler))
    if database_url:
        parsed_database_url = urlparse(database_url)
        if parsed_database_url.hostname and ".pooler.supabase.com" in parsed_database_url.hostname:
            candidates.append(("DATABASE_URL", database_url))
        else:
            candidates.extend(pooler_candidates_from_direct_url(database_url))

    if candidates:
        for label, candidate_url in candidates:
            print(f"trying={label}", flush=True)
            try:
                conn = psycopg.connect(candidate_url, connect_timeout=5)
                print(f"connected_via={label}", flush=True)
                return inspect_connection(conn)
            except Exception as exc:
                print(f"failed={label} error={type(exc).__name__}: {str(exc)[:220]}", flush=True)
        raise SystemExit("Could not connect using IPv4 pooler candidates.")

    if not password:
        raise SystemExit("Missing DATABASE_URL or SUPABASE_PASSWORD.")

    project_ref = urlparse(url).netloc.split(".")[0]
    candidates = [
        *[
            {
                "label": f"pooler-{region}-{port}",
                "host": f"aws-0-{region}.pooler.supabase.com",
                "port": port,
                "user": f"postgres.{project_ref}",
            }
            for region in (
                "sa-east-1",
                "us-east-1",
                "us-east-2",
                "us-west-1",
                "us-west-2",
                "ca-central-1",
                "eu-west-1",
                "eu-west-2",
                "eu-central-1",
                "ap-south-1",
                "ap-southeast-1",
                "ap-southeast-2",
                "ap-northeast-1",
            )
            for port in (6543, 5432)
        ],
    ]

    conn = None
    last_error = ""
    for candidate in candidates:
        print(f"trying={candidate['label']} host={candidate['host']} port={candidate['port']}", flush=True)
        try:
            conn = psycopg.connect(
                host=str(candidate["host"]),
                port=int(candidate["port"]),
                dbname="postgres",
                user=str(candidate["user"]),
                password=password,
                sslmode="require",
                connect_timeout=3,
            )
            print(f"connected_via={candidate['label']}", flush=True)
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            print(f"failed={candidate['label']} error={last_error}", flush=True)

    if conn is None:
        raise SystemExit(f"Could not connect to Supabase Postgres. Last error: {last_error}")

    inspect_connection(conn)


def inspect_connection(conn: psycopg.Connection) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute("select current_database(), current_user, version()")
            db_name, db_user, version = cur.fetchone()
            print(f"connected database={db_name} user={db_user} version={' '.join(version.split()[:2])}")

            cur.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                order by table_name
                """
            )
            tables = [row[0] for row in cur.fetchall()]
            print(f"public_table_count={len(tables)}")
            print("public_tables=" + ",".join(tables[:80]))


if __name__ == "__main__":
    main()
