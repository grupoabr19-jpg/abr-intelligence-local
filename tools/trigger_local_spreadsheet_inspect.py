from __future__ import annotations

import json
import os
import sys

import httpx


def main() -> None:
    base_url = os.environ.get("ABR_API_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("ABR_API_KEY", "")
    input_dir = os.environ.get("ABR_LOCAL_SPREADSHEET_DIR", "Planilhas")

    if not base_url:
        raise SystemExit("ABR_API_BASE_URL nao configurado.")

    headers = {"x-api-key": api_key} if api_key else {}
    url = f"{base_url}/v1/spreadsheets/local/inspect"
    response = httpx.post(url, headers=headers, json={"input_dir": input_dir}, timeout=300)
    payload: object
    try:
        payload = response.json()
    except Exception:
        payload = response.text

    result = {
        "url": url,
        "status_code": response.status_code,
        "response": payload,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if response.status_code < 200 or response.status_code >= 300:
        sys.exit(1)


if __name__ == "__main__":
    main()
