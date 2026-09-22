from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence"
DEFAULT_QUERY_ID = "D0A4D301"


def main(query_id: str = DEFAULT_QUERY_ID) -> None:
    source = EVIDENCE_DIR / f"aster_execute_capture_{query_id}.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    execute_events = [
        event
        for event in data.get("events", [])
        if str(event.get("url", "")).endswith("/execute")
    ]
    latest = execute_events[-1] if execute_events else {}

    summary: dict[str, Any] = {
        "query_id": query_id,
        "target": data.get("target"),
        "final_url": data.get("final_url"),
        "execute_event_count": len(execute_events),
        "aster_post_count": len(data.get("aster_posts", [])),
        "timeout_screenshot": data.get("timeout_screenshot"),
        "successful_execute_event_count": sum(
            1 for event in execute_events if 200 <= int(event.get("status", 0)) < 300
        ),
        "latest_execute_status": latest.get("status"),
        "latest_execute_postData": latest.get("postData"),
        "latest_execute_responseShape": latest.get("responseShape"),
        "latest_execute_responsePreview": latest.get("responsePreview"),
    }

    output_json = EVIDENCE_DIR / f"aster_execute_summary_{query_id}.json"
    output_md = EVIDENCE_DIR / f"aster_execute_summary_{query_id}.md"
    output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    params = (summary.get("latest_execute_postData") or {}).get("params") or {}
    lines = [
        "# Aster Execute Summary",
        "",
        f"Query ID: `{query_id}`",
        f"Execute events: `{summary['execute_event_count']}`",
        f"Aster POST events: `{summary['aster_post_count']}`",
        f"Timeout screenshot: `{summary.get('timeout_screenshot')}`",
        f"Successful execute events: `{summary['successful_execute_event_count']}`",
        f"Latest status: `{summary.get('latest_execute_status')}`",
        "",
        "## Latest POST Params",
    ]
    for key, value in params.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Latest Response",
            "",
            "```json",
            json.dumps(summary.get("latest_execute_responsePreview"), ensure_ascii=False, indent=2),
            "```",
        ]
    )
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "execute_event_count": summary["execute_event_count"],
                "successful_execute_event_count": summary["successful_execute_event_count"],
                "latest_execute_status": summary["latest_execute_status"],
                "output_json": str(output_json.relative_to(ROOT)),
                "output_md": str(output_md.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
