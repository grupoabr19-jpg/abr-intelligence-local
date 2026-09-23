from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIRECT_SCRIPT = ROOT / "tools" / "aster_direct_execute_ingest.py"
EVIDENCE_DIR = ROOT / "docs" / "evidence"


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, 28))


def iter_windows(start: date, end: date, chunk_months: int) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    current = start
    while current <= end:
        next_start = add_months(current, chunk_months)
        current_end = min(end, next_start - timedelta(days=1))
        windows.append((current, current_end))
        current = next_start
    return windows


def parse_stdout(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    start = text.rfind("\n{")
    if start >= 0:
        text = text[start + 1 :]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill direto Aster sem UI.")
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--chunk-months", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-windows", type=int, default=0)
    args = parser.parse_args()

    start = date.fromisoformat(args.date_from)
    end = date.fromisoformat(args.date_to)
    windows = iter_windows(start, end, args.chunk_months)
    if args.max_windows > 0:
        windows = windows[: args.max_windows]

    summary: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "query_id": args.query_id.upper(),
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "chunk_months": args.chunk_months,
        "window_count": len(windows),
        "results": [],
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE_DIR / f"aster_direct_backfill_summary_{args.query_id.upper()}.json"
    for window_start, window_end in windows:
        command = [
            sys.executable,
            str(DIRECT_SCRIPT),
            "--query-id",
            args.query_id.upper(),
            "--date-from",
            window_start.isoformat(),
            "--date-to",
            window_end.isoformat(),
            "--batch-size",
            str(args.batch_size),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        parsed = parse_stdout(completed.stdout)
        result = {
            "date_from": window_start.isoformat(),
            "date_to": window_end.isoformat(),
            "return_code": completed.returncode,
            "rows_captured": (parsed or {}).get("rows_captured"),
            "batch_count": (parsed or {}).get("batch_count"),
            "sync_id": (parsed or {}).get("sync_id"),
            "stdout_tail": completed.stdout[-1000:],
            "stderr_tail": completed.stderr[-2000:],
        }
        summary["results"].append(result)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if completed.returncode != 0:
            break

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    total_rows = sum(item.get("rows_captured") or 0 for item in summary["results"] if item["return_code"] == 0)
    print(
        json.dumps(
            {
                "query_id": summary["query_id"],
                "successful_windows": sum(1 for item in summary["results"] if item["return_code"] == 0),
                "total_rows": total_rows,
                "output_json": str(output.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
