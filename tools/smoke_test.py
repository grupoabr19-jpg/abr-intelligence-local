from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.xlsx_pipeline import iter_xlsx_frames, summarize_xlsx  # noqa: E402


def check_manifest() -> dict[str, object]:
    manifest = ROOT / "extension" / "aster-capture" / "manifest.json"
    json.loads(manifest.read_text(encoding="utf-8"))
    return {"name": "manifest", "ok": True, "path": str(manifest.relative_to(ROOT))}


def check_xlsx(path: Path, sheet: str | None = None) -> dict[str, object]:
    summary = summarize_xlsx(path, sheet_name=sheet, sample_rows=1)
    rows = 0
    chunks = 0
    columns = 0
    for frame in iter_xlsx_frames(path, sheet_name=sheet, chunk_size=10_000):
        chunks += 1
        rows += len(frame)
        columns = len(frame.columns)

    return {
        "name": path.name,
        "ok": rows > 0 and columns > 0,
        "sheet": summary["sheet"],
        "rows": rows,
        "columns": columns,
        "chunks": chunks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    results = [
        check_manifest(),
        check_xlsx(ROOT / "data" / "input" / "GestãodaProdução.xlsx"),
        check_xlsx(ROOT / "data" / "input" / "Margem_GABR_20260916.xlsx", sheet="BD_Meta"),
    ]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for result in results:
            print(result)

    failed = [result for result in results if not result.get("ok")]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
