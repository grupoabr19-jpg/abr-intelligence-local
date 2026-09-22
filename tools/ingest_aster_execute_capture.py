from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERY_ID = "D0A4D301"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def latest_execute_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    execute_events = [
        event
        for event in events
        if str(event.get("url", "")).endswith("/execute") and 200 <= int(event.get("status", 0)) < 300
    ]
    if not execute_events:
        raise SystemExit("Nenhum evento /execute 2xx encontrado na captura.")
    return execute_events[-1]


def chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def post_ingest(env: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        env["ABR_INGEST_URL"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "x-collector-key": env["ABR_COLLECTOR_KEY"],
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"status": response.status, "body": json.loads(body)}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"status": exc.code, "body": body}


def main(query_id: str = DEFAULT_QUERY_ID) -> None:
    env = load_env()
    required = ("ABR_INGEST_URL", "ABR_COLLECTOR_KEY", "ABR_ASTER_FONTE_ID")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise SystemExit("Variaveis ausentes: " + ", ".join(missing))

    capture_path = ROOT / "docs" / "evidence" / f"aster_execute_capture_{query_id}.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    event = latest_execute_event(capture.get("events", []))
    response = event.get("responsePreview") or {}
    rows = response.get("data") or []
    if not isinstance(rows, list) or not rows:
        raise SystemExit("A captura nao contem linhas em responsePreview.data.")

    shape_rows = (((event.get("responseShape") or {}).get("data") or {}).get("length"))
    partial = isinstance(shape_rows, int) and shape_rows > len(rows)
    sync_id = f"ASTER-{query_id}-{int(time.time())}"
    post_params = (event.get("postData") or {}).get("params") or {}
    metadata = {
        "query_id": query_id,
        "report_name": "ABR - Analise de Vendas por Item",
        "source_capture": str(capture_path.relative_to(ROOT)),
        "target": capture.get("target"),
        "final_url": capture.get("final_url"),
        "filters": post_params,
        "columns": response.get("columns") or [],
        "captured_rows_in_file": len(rows),
        "reported_rows_by_aster": shape_rows,
        "is_partial_capture": partial,
    }

    results = []
    for index, batch in enumerate(chunks(rows, 1000), start=1):
        payload = {
            "fonte_id": env["ABR_ASTER_FONTE_ID"],
            "sync_id": sync_id,
            "entidade": f"aster_report_{query_id.lower()}",
            "rows": batch,
            "metadata": {**metadata, "batch_index": index, "batch_rows": len(batch)},
        }
        result = post_ingest(env, payload)
        results.append(result)
        if result["status"] < 200 or result["status"] >= 300:
            raise SystemExit(json.dumps({"sync_id": sync_id, "failed": result}, ensure_ascii=False, indent=2))

    print(
        json.dumps(
            {
                "sync_id": sync_id,
                "query_id": query_id,
                "rows_sent": len(rows),
                "reported_rows_by_aster": shape_rows,
                "is_partial_capture": partial,
                "batch_count": len(results),
                "responses": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
