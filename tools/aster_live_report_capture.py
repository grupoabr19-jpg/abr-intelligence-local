from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Request, Response, async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.manual_auth import has_auth_tokens, save_current_aster_session
from backend.aster_collector.settings import get_settings


EVIDENCE_DIR = ROOT / "docs" / "evidence"
TARGET_URL = "https://aster.gruposps.com.br/ExecuteReport/D0A4D301/c2840840-b5ef-11f1-9bfe-c7e922c97658"
SENSITIVE_HEADER_PARTS = ("authorization", "token", "cookie", "password", "sktid")


def redact_headers(headers: dict[str, str]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in sorted(headers.items()):
        key_lower = key.lower()
        if any(part in key_lower for part in SENSITIVE_HEADER_PARTS):
            redacted[key] = {"redacted": True, "length": len(value or "")}
        else:
            redacted[key] = value
    return redacted


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if any(part in key_lower for part in ("token", "password", "authorization", "email", "cpf", "cnpj")):
                output[str(key)] = "[REDACTED]"
            else:
                output[str(key)] = sanitize_json(item)
        return output
    if isinstance(value, list):
        return [sanitize_json(item) for item in value[:100]]
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + "...[truncated]"
    return value


async def response_preview(response: Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        return None
    try:
        return sanitize_json(await response.json())
    except Exception:
        return None


async def wait_for_login(page, timeout_seconds: int) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_session: dict[str, Any] = {}
    while asyncio.get_running_loop().time() < deadline:
        last_session = await save_current_aster_session(page)
        raw_persist = last_session.get("sessionStorage", {}).get("persist:SPS_AHS")
        if has_auth_tokens(raw_persist):
            return last_session
        await page.wait_for_timeout(2_000)
    return last_session


async def main_async(timeout_seconds: int = 600) -> dict[str, Any]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    events: list[dict[str, Any]] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, slow_mo=150)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)

        async def on_response(response: Response) -> None:
            request: Request = response.request
            url = response.url
            if "astersrv.gruposps.com.br" not in url:
                return
            events.append(
                {
                    "method": request.method,
                    "url": url,
                    "status": response.status,
                    "requestHeaders": redact_headers(await request.all_headers()),
                    "responseContentType": response.headers.get("content-type", ""),
                    "responsePreview": await response_preview(response),
                }
            )

        page.on("response", lambda response: asyncio.create_task(on_response(response)))

        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        session = await wait_for_login(page, timeout_seconds)
        if not session.get("hasAsterAuthTokens"):
            await context.close()
            await browser.close()
            return {
                "savedAt": datetime.now(timezone.utc).isoformat(),
                "hasAsterAuthTokens": False,
                "event_count": len(events),
                "events": events,
                "warning": "Timeout antes de detectar tokens do Aster.",
            }

        await page.goto(TARGET_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(20_000)
        final_session = await save_current_aster_session(page)

        result = {
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "hasAsterAuthTokens": bool(final_session.get("hasAsterAuthTokens")),
            "target": TARGET_URL,
            "final_url": page.url,
            "event_count": len(events),
            "events": events,
        }

        await context.close()
        await browser.close()

    (EVIDENCE_DIR / "aster_live_report_capture.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(result)
    return result


def write_markdown(result: dict[str, Any]) -> None:
    lines = [
        "# Aster Live Report Capture",
        "",
        f"Has auth tokens: `{result.get('hasAsterAuthTokens')}`",
        f"Target: `{result.get('target')}`",
        f"Final URL: `{result.get('final_url')}`",
        f"Events: `{result.get('event_count')}`",
        "",
        "## Requests",
    ]
    for item in result.get("events", []):
        lines.append(f"- `{item['status']}` `{item['method']}` {item['url']}")
        auth = item.get("requestHeaders", {}).get("authorization")
        if isinstance(auth, dict):
            lines.append(f"  - authorization length: `{auth.get('length')}`")
    (EVIDENCE_DIR / "aster_live_report_capture.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    result = asyncio.run(main_async())
    print(
        json.dumps(
            {
                "hasAsterAuthTokens": result.get("hasAsterAuthTokens"),
                "event_count": result.get("event_count"),
                "final_url": result.get("final_url"),
                "output_json": "docs/evidence/aster_live_report_capture.json",
                "output_md": "docs/evidence/aster_live_report_capture.md",
                "warning": result.get("warning"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
