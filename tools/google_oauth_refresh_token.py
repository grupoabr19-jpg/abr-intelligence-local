from __future__ import annotations

import argparse
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.archive_storage import DRIVE_SCOPE
from tools.apply_migrations import load_env


REDIRECT_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    server: "OAuthServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        self.server.auth_code = query.get("code", [""])[0]
        self.server.auth_error = query.get("error", [""])[0]
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>Autorizacao recebida.</h1><p>Pode voltar ao terminal.</p></body></html>"
        )

    def log_message(self, format: str, *args: object) -> None:
        return


class OAuthServer(HTTPServer):
    auth_code: str = ""
    auth_error: str = ""


def update_env_file(refresh_token: str) -> None:
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for index, line in enumerate(lines):
        if line.startswith("GOOGLE_OAUTH_REFRESH_TOKEN="):
            lines[index] = f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}"
            updated = True
            break
    if not updated:
        lines.append(f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera GOOGLE_OAUTH_REFRESH_TOKEN para upload no Google Drive.")
    parser.add_argument("--no-browser", action="store_true", help="Nao tenta abrir o navegador automaticamente.")
    parser.add_argument("--print-token", action="store_true", help="Imprime o refresh token. Evite usar.")
    args = parser.parse_args()

    env = load_env()
    client_id = env.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = env.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit("Configure GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET no .env.")

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": DRIVE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    server = OAuthServer(("127.0.0.1", REDIRECT_PORT), OAuthCallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("Abra esta URL e autorize o acesso ao Google Drive:")
    print(url)
    if not args.no_browser:
        webbrowser.open(url)

    thread.join(timeout=300)
    server.server_close()

    if server.auth_error:
        raise SystemExit(f"OAuth retornou erro: {server.auth_error}")
    if not server.auth_code:
        raise SystemExit("Nenhum codigo OAuth recebido em 5 minutos.")

    with httpx.Client(timeout=60) as client:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": server.auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            },
        )
        response.raise_for_status()
        token_data = response.json()

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise SystemExit("Google nao retornou refresh_token. Revogue o app e rode novamente com prompt=consent.")

    update_env_file(str(refresh_token))
    print("GOOGLE_OAUTH_REFRESH_TOKEN salvo no .env.")
    if args.print_token:
        print(refresh_token)


if __name__ == "__main__":
    main()
