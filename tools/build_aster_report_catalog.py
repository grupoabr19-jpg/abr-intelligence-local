from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence"
CAPTURE_PATH = EVIDENCE_DIR / "aster_live_report_capture.json"
OUTPUT_JSON = EVIDENCE_DIR / "aster_report_catalog.json"
OUTPUT_MD = EVIDENCE_DIR / "aster_report_catalog.md"


def find_response(events: list[dict[str, Any]], url_suffix: str) -> Any:
    for event in events:
        if str(event.get("url", "")).endswith(url_suffix):
            return event.get("responsePreview")
    return None


def walk_menu(node: Any, path: str = "") -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            reports.extend(walk_menu(item, path))
        return reports

    if not isinstance(node, dict):
        return reports

    name = node.get("name") or str(node.get("id") or "")
    route = node.get("route")
    current_path = "/".join(part for part in (path, str(name)) if part)

    if node.get("isReport") or (isinstance(route, str) and "ExecuteReport" in route):
        reports.append(
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "route": route,
                "description": node.get("description"),
                "path": current_path,
                "group": node.get("group"),
                "modules": node.get("modules"),
            }
        )

    for key in ("items", "subMenus"):
        for child in node.get(key) or []:
            reports.extend(walk_menu(child, current_path))
    return reports


def extract_query_id_from_url(url: str) -> str | None:
    marker = "/APP/CRM/ReportQueries/"
    if marker not in url:
        return None
    tail = url.split(marker, 1)[1]
    return tail.split("/", 1)[0] or None


def main() -> None:
    capture = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    events = capture.get("events", [])
    menu = find_response(events, "/main_menu/user") or []
    reports = walk_menu(menu)

    report_queries: dict[str, dict[str, Any]] = {}
    for event in events:
        url = str(event.get("url", ""))
        query_id = extract_query_id_from_url(url)
        if not query_id:
            continue
        report_queries.setdefault(query_id, {"query_id": query_id})
        if url.endswith("/parameters"):
            report_queries[query_id]["parameters"] = event.get("responsePreview")
        elif url.endswith("/settings"):
            report_queries[query_id]["settings"] = event.get("responsePreview")
        elif url.endswith("/check_permission"):
            report_queries[query_id]["check_permission"] = event.get("responsePreview")
        elif url.endswith("/execute"):
            report_queries[query_id]["execute_preview"] = event.get("responsePreview")

    result = {
        "source_capture": str(CAPTURE_PATH.relative_to(ROOT)),
        "report_menu_count": len(reports),
        "report_query_count": len(report_queries),
        "reports": reports,
        "report_queries": sorted(report_queries.values(), key=lambda item: item["query_id"]),
    }
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Aster Report Catalog",
        "",
        f"Source capture: `{result['source_capture']}`",
        f"Report menu count: `{result['report_menu_count']}`",
        f"Report query count: `{result['report_query_count']}`",
        "",
        "## Captured ReportQueries",
    ]
    for query in result["report_queries"]:
        params = query.get("parameters") or {}
        name = params.get("name") or params.get("description") or query["query_id"]
        lines.append(f"- `{query['query_id']}` {name}")
        for param in params.get("parameters") or []:
            required = " required" if param.get("required") else ""
            lines.append(
                f"  - `{param.get('name')}` {param.get('label')} ({param.get('type')}{required})"
            )

    lines.extend(["", "## Menu Reports"])
    for report in reports:
        lines.append(f"- `{report.get('route')}` {report.get('path')}")

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "report_menu_count": len(reports),
                "report_query_count": len(report_queries),
                "output_json": str(OUTPUT_JSON.relative_to(ROOT)),
                "output_md": str(OUTPUT_MD.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
