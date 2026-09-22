from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


def post(env: dict[str, str], payload: dict) -> dict:
    request = urllib.request.Request(
        env["ABR_INGEST_URL"],
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json", "x-collector-key": env["ABR_COLLECTOR_KEY"]},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    env = load_env()
    sync_id = f"SMOKE-ACCUM-{int(time.time())}"
    common = {
        "fonte_id": env["ABR_ASTER_FONTE_ID"],
        "sync_id": sync_id,
        "entidade": "diagnostico_acumulacao",
        "metadata": {"teste": True},
    }
    first = post(env, {**common, "rows": [{"id": "a"}, {"id": "b"}]})
    second = post(env, {**common, "rows": [{"id": "c"}, {"id": "d"}, {"id": "e"}]})

    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select registros_lidos, registros_inseridos
                from public.historico_importacoes
                where sync_id = %s
                """,
                (sync_id,),
            )
            historico = cur.fetchone()
            cur.execute("delete from public.staging_dados where sync_id = %s", (sync_id,))
            cur.execute("delete from public.historico_importacoes where sync_id = %s", (sync_id,))
            conn.commit()

    print(
        json.dumps(
            {
                "sync_id": sync_id,
                "first": first,
                "second": second,
                "historico": historico,
                "cleanup": "ok",
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
