from __future__ import annotations

import argparse
import json
import subprocess
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_core_database, load_env


QUERY_ID = "D0A4D301"


def month_starts(start: date, end: date) -> list[date]:
    months: list[date] = []
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while current <= last:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def month_bounds(month_start: date, start: date, end: date) -> tuple[date, date]:
    month_end = date(month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1])
    return max(start, month_start), min(end, month_end)


def run_command(command: list[str], timeout_seconds: int) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    stdout = completed.stdout.strip()
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
    return {
        "command": command,
        "return_code": completed.returncode,
        "stdout_tail": stdout[-3000:],
        "stderr_tail": completed.stderr.strip()[-3000:],
        "parsed": parsed,
    }


def count_sales_fact() -> dict[str, Any]:
    env = load_env()
    with connect_core_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                  count(*)::int,
                  min(sale_date),
                  max(sale_date),
                  coalesce(sum(valor_total), 0)
                from public.dashboard_sales_fact
                """
            )
            rows, min_date, max_date, total = cur.fetchone()
    return {
        "rows": rows,
        "date_min": min_date.isoformat() if min_date else None,
        "date_max": max_date.isoformat() if max_date else None,
        "valor_total": f"{total:.2f}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega vendas do Aster mes a mes e atualiza o cache de negocio.")
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    start = date.fromisoformat(args.date_from)
    end = date.fromisoformat(args.date_to)
    results: list[dict[str, Any]] = []
    failures = 0

    for month_start in month_starts(start, end):
        date_from, date_to = month_bounds(month_start, start, end)
        month_key = month_start.strftime("%Y-%m")
        ingest = run_command(
            [
                sys.executable,
                str(ROOT / "tools" / "aster_live_execute_ingest.py"),
                "--query-id",
                QUERY_ID,
                "--date-from",
                date_from.isoformat(),
                "--date-to",
                date_to.isoformat(),
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            timeout_seconds=args.timeout_seconds + 90,
        )
        item: dict[str, Any] = {"month": month_key, "date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "ingest": ingest}
        if ingest["return_code"] != 0:
            failures += 1
            results.append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
            if args.stop_on_error:
                break
            continue

        refresh_fact = run_command([sys.executable, str(ROOT / "tools" / "refresh_aster_sales_fact.py")], timeout_seconds=300)
        refresh_cache = run_command(
            [
                sys.executable,
                str(ROOT / "tools" / "refresh_dashboard_sales_cache.py"),
                "--date-from",
                start.isoformat(),
                "--date-to",
                date_to.isoformat(),
            ],
            timeout_seconds=300,
        )
        item["refresh_fact"] = refresh_fact
        item["refresh_cache"] = refresh_cache
        item["sales_fact"] = count_sales_fact()
        if refresh_fact["return_code"] != 0 or refresh_cache["return_code"] != 0:
            failures += 1
        results.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if failures and args.stop_on_error:
            break

    summary = {"failures": failures, "months": len(results), "sales_fact": count_sales_fact(), "results": results}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
