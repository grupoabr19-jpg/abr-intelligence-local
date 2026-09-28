from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 a partir de um JSON.")
    parser.add_argument("json_path", help="Caminho do arquivo JSON da service account.")
    args = parser.parse_args()

    path = Path(args.json_path)
    data = path.read_text(encoding="utf-8")
    parsed = json.loads(data)
    if parsed.get("type") != "service_account" or not parsed.get("client_email") or not parsed.get("private_key"):
        raise SystemExit("O arquivo informado nao parece ser uma service account valida.")

    encoded = base64.b64encode(data.encode("utf-8")).decode("ascii")
    print("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=" + encoded)


if __name__ == "__main__":
    main()
