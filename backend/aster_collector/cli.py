import argparse
import asyncio
import json

from .browser_capture import run_aster_session
from .explorer import explore_aster
from .manual_auth import manual_login
from .xlsx_pipeline import summarize_xlsx


def main() -> None:
    parser = argparse.ArgumentParser(prog="abr-python")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect-xlsx")
    inspect.add_argument("path")
    inspect.add_argument("--sheet")

    sub.add_parser("run-aster")
    manual_login_cmd = sub.add_parser("manual-login-aster")
    manual_login_cmd.add_argument("--timeout-seconds", type=int, default=600)
    explore = sub.add_parser("explore-aster")
    explore.add_argument("--max-clicks", type=int, default=30)

    args = parser.parse_args()

    if args.command == "inspect-xlsx":
        print(json.dumps(summarize_xlsx(args.path, args.sheet), ensure_ascii=False, indent=2, default=str))
    elif args.command == "run-aster":
        print(json.dumps(asyncio.run(run_aster_session()), ensure_ascii=False, indent=2, default=str))
    elif args.command == "manual-login-aster":
        print(
            json.dumps(
                asyncio.run(manual_login(timeout_seconds=args.timeout_seconds)),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    elif args.command == "explore-aster":
        result = asyncio.run(explore_aster(max_clicks=args.max_clicks))
        print(
            json.dumps(
                {
                    "login_status": result["login_status"],
                    "page_count": result["page_count"],
                    "network_count": result["network_count"],
                    "output_json": "docs/evidence/aster_exploration.json",
                    "output_md": "docs/evidence/aster_exploration.md",
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


if __name__ == "__main__":
    main()
