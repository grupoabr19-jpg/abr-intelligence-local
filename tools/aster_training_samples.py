from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


def distinct_payload_values(cur, key: str, limit: int = 20) -> list[str]:
    cur.execute(
        """
        select distinct payload_original ->> %s as value
        from public.staging_dados
        where entidade = 'aster_report_d0a4d301'
          and payload_original ? %s
          and coalesce(payload_original ->> %s, '') <> ''
        order by value
        limit %s
        """,
        (key, key, key, limit),
    )
    return [row[0] for row in cur.fetchall()]


def main() -> None:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            result = {
                "clientes": distinct_payload_values(cur, "CodCliente"),
                "familias": distinct_payload_values(cur, "Familia"),
                "itens": distinct_payload_values(cur, "Item"),
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
