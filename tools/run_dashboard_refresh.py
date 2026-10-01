from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api.update_orchestrator import dashboard_refresh_manager


TERMINAL_STATUSES = {"succeeded", "partial", "failed", "skipped"}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


async def run(args: argparse.Namespace) -> int:
    job = await dashboard_refresh_manager.start_refresh(
        mode=args.mode,
        date_from=parse_date(args.date_from),
        date_to=parse_date(args.date_to),
        force=args.force,
    )
    serialized: dict[str, Any] | None = dashboard_refresh_manager.serialize_job(job)
    while serialized and serialized.get("status") not in TERMINAL_STATUSES:
        await asyncio.sleep(args.poll_seconds)
        status = await dashboard_refresh_manager.status()
        serialized = status.get("current") or (status.get("history") or [None])[0] or serialized

    print(json.dumps({"job": serialized}, ensure_ascii=False, indent=2, default=str))
    if not serialized:
        return 1
    return 1 if serialized.get("status") == "failed" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa a atualizacao completa do dashboard fora do Web Service.")
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto")
    parser.add_argument("--date-from", default=None)
    parser.add_argument("--date-to", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
