from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.local_spreadsheets import (  # noqa: E402
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_JSON,
    DEFAULT_OUTPUT_MD,
    inspect_local_spreadsheet_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    result = inspect_local_spreadsheet_sources(
        input_dir=args.input_dir,
        output_json=args.output_json,
        output_md=args.output_md,
    )
    print(
        json.dumps(
            {
                "files": result["files"],
                "input_dir": result["input_dir"],
                "output_json": result["output_json"],
                "output_md": result["output_md"],
                "warning": result["warning"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
