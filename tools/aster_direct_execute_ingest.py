from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.aster_collector.manual_auth import AUTH_STATE_PATH, parse_persist_state
from backend.aster_collector.report_registry import DateFieldBinding, ReportConfig, get_report_config
from tools.aster_live_execute_ingest import chunks, load_env, post_ingest, static_param_overrides


EVIDENCE_DIR = ROOT / "docs" / "evidence"
ASTER_EXECUTE_URL = "https://astersrv.gruposps.com.br/APP/CRM/ReportQueries/{query_id}/execute"


def to_aster_datetime(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return value
    return f"{value}T03:00:00.000Z"


def load_company_token() -> str:
    if not AUTH_STATE_PATH.exists():
        raise SystemExit(
            f"Sessao Aster salva nao encontrada em {AUTH_STATE_PATH.relative_to(ROOT)}. "
            "Rode o login/captura uma vez antes do execute direto."
        )

    session = json.loads(AUTH_STATE_PATH.read_text(encoding="utf-8"))
    local_storage = session.get("localStorage") or {}
    session_storage = session.get("sessionStorage") or {}
    persist_state = parse_persist_state(session_storage.get("persist:SPS_AHS"))
    token = local_storage.get("companyToken") or persist_state.get("companyToken")
    if not token:
        raise SystemExit("companyToken ausente na sessao Aster salva.")
    return str(token)


def date_params(report: ReportConfig, date_from: str, date_to: str) -> dict[str, str]:
    if not report.date_fields:
        return {}
    values = [to_aster_datetime(date_from), to_aster_datetime(date_to)]
    params: dict[str, str] = {}
    for binding, value in zip(report.date_fields, values):
        params[binding.param_name] = value
    return params


def default_params(query_id: str, report: ReportConfig) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if query_id.upper() == "D0A4D301":
        params.update(
            {
                "Item": None,
                "PN": None,
                "TIPO": "",
                "_FILIAL": "Todos",
                "Filial": None,
            }
        )
    params.update(static_param_overrides(report.static_fields))
    for field in report.text_fields:
        params[field.param_name] = field.value
    return params


def execute_report(query_id: str, params: dict[str, Any]) -> dict[str, Any]:
    token = load_company_token()
    request = urllib.request.Request(
        ASTER_EXECUTE_URL.format(query_id=query_id),
        data=json.dumps({"params": params}, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {token}",
            "connectionalias": "Aster",
            "content-type": "application/json;charset=UTF-8",
            "locale": "pt-BR",
            "origin": "https://aster.gruposps.com.br",
            "referer": "https://aster.gruposps.com.br/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "status": response.status,
                "url": response.url,
                "postData": {"params": params},
                "body": json.loads(body),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            json.dumps(
                {
                    "error": "Falha HTTP no execute direto Aster.",
                    "status": exc.code,
                    "body": body[-2000:],
                    "params": params,
                },
                ensure_ascii=False,
                indent=2,
            )
        ) from exc


def ingest_execute(query_id: str, execute: dict[str, Any], batch_size: int) -> dict[str, Any]:
    env = load_env()
    required = ("ABR_INGEST_URL", "ABR_COLLECTOR_KEY", "ABR_ASTER_FONTE_ID")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise SystemExit("Variaveis ausentes: " + ", ".join(missing))

    report = get_report_config(query_id)
    body = execute.get("body") or {}
    rows = body.get("data") or []
    if not isinstance(rows, list) or not rows:
        if report.automation_status == "validated_empty":
            rows = []
        else:
            raise SystemExit("O execute direto nao retornou linhas em body.data.")

    sync_id = f"ASTER-{query_id}-{int(time.time())}"
    columns = body.get("columns") or []
    post_params = (execute.get("postData") or {}).get("params") or {}
    metadata = {
        "query_id": query_id,
        "report_area": report.area,
        "report_name": report.name,
        "filters": post_params,
        "automation": {
            "auto_execute": True,
            "report_name": report.name,
            "automation_status": report.automation_status,
            "clicked": "backend_direct_execute",
        },
        "columns": columns,
        "captured_rows": len(rows),
        "final_url": execute.get("url"),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "ingestion_mode": "backend_direct_execute",
    }

    responses = []
    for index, batch in enumerate(chunks(rows, batch_size), start=1):
        payload = {
            "fonte_id": env["ABR_ASTER_FONTE_ID"],
            "sync_id": sync_id,
            "entidade": report.entity,
            "rows": batch,
            "metadata": {**metadata, "batch_index": index, "batch_rows": len(batch)},
        }
        result = post_ingest(env, payload)
        responses.append(result)
        if result["status"] < 200 or result["status"] >= 300:
            raise SystemExit(json.dumps({"sync_id": sync_id, "failed": result}, ensure_ascii=False, indent=2))

    return {
        "sync_id": sync_id,
        "query_id": query_id,
        "rows_captured": len(rows),
        "batch_count": len(responses),
        "responses": responses,
        "columns_count": len(columns),
        "filters": post_params,
        "automation": metadata["automation"],
        "batch_size": batch_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa e ingere relatorio Aster sem automacao de UI.")
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--date-from", default="2026-09-01")
    parser.add_argument("--date-to", default="2026-09-30")
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size deve ser >= 1.")

    query_id = args.query_id.upper()
    report = get_report_config(query_id)
    params = {
        **default_params(query_id, report),
        **date_params(report, args.date_from, args.date_to),
    }
    execute = execute_report(query_id, params)
    summary = ingest_execute(query_id, execute, args.batch_size)

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE_DIR / f"aster_direct_ingest_summary_{query_id}.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    printable = {**summary, "output_json": str(output.relative_to(ROOT))}
    if not args.verbose:
        printable["responses"] = {
            "count": len(summary["responses"]),
            "all_status_2xx": all(200 <= item.get("status", 0) < 300 for item in summary["responses"]),
            "last": summary["responses"][-1] if summary["responses"] else None,
        }
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
