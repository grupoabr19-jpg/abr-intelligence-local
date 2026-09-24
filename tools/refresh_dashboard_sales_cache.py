from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.api.data import write_sales_summary_cache


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualiza cache do resumo comercial do dashboard.")
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    args = parser.parse_args()

    payload = write_sales_summary_cache(
        date_from=parse_date(args.date_from),
        date_to=parse_date(args.date_to),
    )
    print(
        json.dumps(
            {
                "date_from": args.date_from,
                "date_to": args.date_to,
                "linhas": payload.get("linhas"),
                "valor_total": payload.get("valor_total"),
                "monthly_count": len(payload.get("monthly", [])),
                "families_count": len(payload.get("families", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
