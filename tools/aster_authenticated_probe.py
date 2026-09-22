from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.browser_capture import try_login
from backend.aster_collector.manual_auth import AUTH_STATE_PATH, parse_persist_state, restore_aster_session
from backend.aster_collector.settings import get_settings


EVIDENCE_DIR = ROOT / "docs" / "evidence"
API_BASE = "https://astersrv.gruposps.com.br"

ENDPOINTS = [
    "/main_menu/user",
    "/ReportQueries",
    "/APP/CRM/ReportQueries",
    "/APP/CRM/ReportQueries/insights",
    "/GlobalContext",
    "/company_users/startPage",
]

DIRECT_ENDPOINTS = [
    "/main_menu/user",
    "/GlobalContext",
    "/company_users/startPage",
    "/applications/EXECUTEREPORT/settings",
    "/APP/CRM/ReportQueries",
    "/APP/CRM/ReportQueries/insights",
    "/APP/CRM/ReportQueries/0F75E84D/parameters",
    "/APP/CRM/ReportQueries/0F75E84D/settings",
    "/APP/CRM/ReportQueries/0F75E84D/check_permission",
    "/APP/CRM/ReportQueries/AB439998/parameters",
    "/APP/CRM/ReportQueries/AB439998/settings",
    "/APP/CRM/ReportQueries/AB439998/check_permission",
]

SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "email",
    "mail",
    "phone",
    "telefone",
    "cpf",
    "cnpj",
}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(sensitive in key_text.lower() for sensitive in SENSITIVE_KEYS):
                clean[key_text] = "[REDACTED]"
            else:
                clean[key_text] = sanitize(item)
        return clean
    if isinstance(value, list):
        return [sanitize(item) for item in value[:500]]
    return value


def parse_nested_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return parse_nested_json(json.loads(value))
        except Exception:
            return value
    if isinstance(value, dict):
        return {key: parse_nested_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [parse_nested_json(item) for item in value]
    return value


def shape_only(value: Any) -> Any:
    value = parse_nested_json(value)
    if isinstance(value, dict):
        return {key: shape_only(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape_only(item) for item in value[:20]]
    if isinstance(value, str):
        return f"[str len {len(value)}]"
    return f"[{type(value).__name__}]"


def collect_interesting(value: Any, path: str = "") -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if isinstance(value, dict):
        lowered_keys = {str(key).lower(): key for key in value.keys()}
        interesting = {}
        for name in (
            "name",
            "label",
            "title",
            "description",
            "path",
            "route",
            "url",
            "code",
            "reportcode",
            "reportname",
            "reportbaseid",
            "docentry",
            "id",
        ):
            if name in lowered_keys:
                key = lowered_keys[name]
                interesting[str(key)] = value.get(key)
        if interesting:
            results.append({"path": path, **sanitize(interesting)})
        for key, item in value.items():
            results.extend(collect_interesting(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            results.extend(collect_interesting(item, f"{path}[{index}]"))
    return results


def load_saved_tokens() -> dict[str, str]:
    if not AUTH_STATE_PATH.exists():
        return {}

    state = json.loads(AUTH_STATE_PATH.read_text(encoding="utf-8"))
    tokens: dict[str, str] = {}
    for storage_name in ("localStorage", "sessionStorage"):
        storage = state.get(storage_name, {})
        if not isinstance(storage, dict):
            continue
        for key in ("authorizationToken", "companyToken"):
            value = storage.get(key)
            if isinstance(value, str) and value:
                tokens[key] = value

    persist_state = parse_persist_state(state.get("sessionStorage", {}).get("persist:SPS_AHS"))
    for key in ("authorizationToken", "companyToken"):
        value = persist_state.get(key)
        if isinstance(value, str) and value:
            tokens[key] = value
    return tokens


def compact_body(response: httpx.Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return sanitize(response.json())
        except Exception:
            return response.text[:2000]
    return response.text[:2000]


async def direct_http_probe() -> list[dict[str, Any]]:
    tokens = load_saved_tokens()
    attempts: list[dict[str, Any]] = []
    base_headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "connectionalias": "Aster",
        "locale": "pt-BR",
        "origin": "https://aster.gruposps.com.br",
        "referer": "https://aster.gruposps.com.br/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome Safari/537.36",
    }
    token_modes = [
        ("authorizationToken", tokens.get("authorizationToken")),
        ("companyToken", tokens.get("companyToken")),
    ]

    async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
        for token_name, token in token_modes:
            if not token:
                attempts.append({"token_mode": token_name, "error": "token ausente"})
                continue

            headers = {**base_headers, "authorization": f"Bearer {token}"}
            for endpoint in DIRECT_ENDPOINTS:
                url = API_BASE + endpoint
                try:
                    response = await client.get(url, headers=headers)
                    body = compact_body(response)
                    attempts.append(
                        {
                            "token_mode": token_name,
                            "endpoint": endpoint,
                            "status": response.status_code,
                            "contentType": response.headers.get("content-type", ""),
                            "body": body,
                        }
                    )
                except Exception as exc:
                    attempts.append(
                        {
                            "token_mode": token_name,
                            "endpoint": endpoint,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
    return attempts


async def fetch_in_page(page, endpoint: str) -> dict[str, Any]:
    url = endpoint if endpoint.startswith("http") else API_BASE + endpoint
    return await page.evaluate(
        """async ({ url }) => {
          const response = await fetch(url, { credentials: 'include' })
          const contentType = response.headers.get('content-type') || ''
          let body
          if (contentType.includes('json')) {
            body = await response.json()
          } else {
            body = await response.text()
          }
          return { url, status: response.status, contentType, body }
        }""",
        {"url": url},
    )


async def main_async() -> dict[str, Any]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    result: dict[str, Any] = {
        "login_status": None,
        "session_shape": {},
        "endpoints": [],
        "direct_http": [],
        "interesting": [],
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.headless)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)
        restored = await restore_aster_session(page)
        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        result["login_status"] = "restored_auth_state" if restored else await try_login(page, settings)
        await page.wait_for_timeout(3_000)
        result["session_shape"] = await page.evaluate(
            """() => ({
              url: location.href,
              localStorageKeys: Object.keys(localStorage),
              sessionStorageKeys: Object.keys(sessionStorage),
              persistShape: sessionStorage.getItem('persist:SPS_AHS')
            })"""
        )
        result["session_shape"]["persistShape"] = shape_only(result["session_shape"].get("persistShape"))

        for endpoint in ENDPOINTS:
            try:
                response = await fetch_in_page(page, endpoint)
                body = sanitize(response["body"])
                item = {
                    "endpoint": endpoint,
                    "url": response["url"],
                    "status": response["status"],
                    "contentType": response["contentType"],
                    "body": body,
                }
                result["endpoints"].append(item)
                result["interesting"].extend(collect_interesting(body, endpoint))
            except Exception as exc:
                result["endpoints"].append({"endpoint": endpoint, "error": f"{type(exc).__name__}: {exc}"})

        await context.close()
        await browser.close()

    result["direct_http"] = await direct_http_probe()
    for item in result["direct_http"]:
        result["interesting"].extend(collect_interesting(item.get("body"), item.get("endpoint", "")))

    (EVIDENCE_DIR / "aster_authenticated_probe.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(result)
    return result


def write_markdown(result: dict[str, Any]) -> None:
    lines = [
        "# Aster Authenticated Probe",
        "",
        f"Login status: `{result['login_status']}`",
        "",
        "## Session Shape",
        "",
        "```json",
        json.dumps(result.get("session_shape", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Endpoints",
    ]
    for endpoint in result["endpoints"]:
        status = endpoint.get("status", "ERR")
        content_type = endpoint.get("contentType", "")
        lines.append(f"- `{status}` `{endpoint['endpoint']}` {content_type}")
        if endpoint.get("error"):
            lines.append(f"  - {endpoint['error']}")

    lines.extend(["", "## Direct HTTP Probe"])
    for item in result.get("direct_http", []):
        status = item.get("status", "ERR")
        token_mode = item.get("token_mode", "")
        content_type = item.get("contentType", "")
        endpoint = item.get("endpoint", "")
        lines.append(f"- `{status}` `{token_mode}` `{endpoint}` {content_type}")
        if item.get("error"):
            lines.append(f"  - {item['error']}")

    lines.append("")
    lines.append("## Interesting Items")
    seen = set()
    for item in result["interesting"]:
        text = json.dumps(item, ensure_ascii=False, default=str)
        if text in seen:
            continue
        seen.add(text)
        lines.append(f"- `{item.get('path', '')}` {text}")

    (EVIDENCE_DIR / "aster_authenticated_probe.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    result = asyncio.run(main_async())
    print(
        json.dumps(
            {
                "login_status": result["login_status"],
                "endpoint_count": len(result["endpoints"]),
                "direct_http_count": len(result["direct_http"]),
                "interesting_count": len(result["interesting"]),
                "output_json": "docs/evidence/aster_authenticated_probe.json",
                "output_md": "docs/evidence/aster_authenticated_probe.md",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
