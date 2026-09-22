from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path


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


def main() -> None:
    env = load_env()
    missing = [
        key
        for key in ("ABR_INGEST_URL", "ABR_COLLECTOR_KEY", "ABR_ASTER_FONTE_ID")
        if not env.get(key)
    ]
    if missing:
        raise SystemExit("Variaveis ausentes: " + ", ".join(missing))

    sync_id = f"SMOKE-EDGE-{int(time.time())}"
    payload = {
        "fonte_id": env["ABR_ASTER_FONTE_ID"],
        "sync_id": sync_id,
        "entidade": "diagnostico_edge_function",
        "rows": [
            {
                "teste": True,
                "origem": "codex_smoke",
                "timestamp": sync_id,
            }
        ],
        "metadata": {"teste": True, "tipo": "smoke"},
    }

    request = urllib.request.Request(
        env["ABR_INGEST_URL"],
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "x-collector-key": env["ABR_COLLECTOR_KEY"],
        },
    )

    print(f"sync_id={sync_id}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"status={response.status}")
            print(response.read().decode("utf-8", errors="replace")[:1000])
    except urllib.error.HTTPError as exc:
        print(f"status={exc.code}")
        print(exc.read().decode("utf-8", errors="replace")[:1000])
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"error={type(exc).__name__}: {str(exc)[:500]}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
