from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.aster_collector.report_registry import REPORTS, ReportConfig


EVIDENCE_DIR = ROOT / "docs" / "evidence"
INGEST_SCRIPT = ROOT / "tools" / "aster_live_execute_ingest.py"


@dataclass(frozen=True)
class BackfillWindow:
    query_id: str
    date_from: date | None
    date_to: date | None


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, 28)
    return date(year, month, day)


def iter_windows(query_id: str, report: ReportConfig, start: date, end: date, chunk_months: int) -> list[BackfillWindow]:
    if not report.date_fields:
        return [BackfillWindow(query_id=query_id, date_from=None, date_to=None)]

    windows: list[BackfillWindow] = []
    current = start
    while current <= end:
        next_start = add_months(current, chunk_months)
        current_end = min(end, next_start - timedelta(days=1))
        windows.append(BackfillWindow(query_id=query_id, date_from=current, date_to=current_end))
        current = next_start
    return windows


def selected_reports(query_ids: list[str], include_empty: bool) -> list[tuple[str, ReportConfig]]:
    if query_ids:
        return [(query_id.upper(), REPORTS[query_id.upper()]) for query_id in query_ids if query_id.upper() in REPORTS]

    allowed_statuses = {"validated"}
    if include_empty:
        allowed_statuses.add("validated_empty")

    return [
        (query_id, report)
        for query_id, report in sorted(REPORTS.items())
        if report.automation_status in allowed_statuses
    ]


def run_window(window: BackfillWindow, timeout_seconds: int) -> dict[str, Any]:
    command = [
        sys.executable,
        str(INGEST_SCRIPT),
        "--query-id",
        window.query_id,
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if window.date_from and window.date_to:
        command.extend(["--date-from", window.date_from.isoformat(), "--date-to", window.date_to.isoformat()])

    started_at = datetime.now(timezone.utc)
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    finished_at = datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "query_id": window.query_id,
        "date_from": window.date_from.isoformat() if window.date_from else None,
        "date_to": window.date_to.isoformat() if window.date_to else None,
        "return_code": completed.returncode,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    try:
        result["parsed_stdout"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result["parsed_stdout"] = None
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa backfill historico dos relatorios Aster validados.")
    parser.add_argument("--date-from", default="2017-01-01")
    parser.add_argument("--date-to", default=date.today().isoformat())
    parser.add_argument("--chunk-months", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--query-id", action="append", default=[])
    parser.add_argument("--include-empty", action="store_true")
    parser.add_argument("--max-windows", type=int, default=0, help="0 executa todas as janelas planejadas.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start = date.fromisoformat(args.date_from)
    end = date.fromisoformat(args.date_to)
    if start > end:
        raise SystemExit("--date-from nao pode ser maior que --date-to.")
    if args.chunk_months < 1:
        raise SystemExit("--chunk-months deve ser >= 1.")

    reports = selected_reports(args.query_id, args.include_empty)
    windows: list[BackfillWindow] = []
    for query_id, report in reports:
        windows.extend(iter_windows(query_id, report, start, end, args.chunk_months))

    if args.max_windows > 0:
        windows = windows[: args.max_windows]

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE_DIR / "aster_historical_backfill_summary.json"
    summary: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "chunk_months": args.chunk_months,
        "dry_run": args.dry_run,
        "window_count": len(windows),
        "windows": [
            {
                "query_id": item.query_id,
                "date_from": item.date_from.isoformat() if item.date_from else None,
                "date_to": item.date_to.isoformat() if item.date_to else None,
            }
            for item in windows
        ],
        "results": [],
    }

    if not args.dry_run:
        for window in windows:
            result = run_window(window, timeout_seconds=args.timeout_seconds)
            summary["results"].append(result)
            output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            if result["return_code"] != 0:
                break

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "output_json": str(output.relative_to(ROOT))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
