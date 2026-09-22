from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from .settings import Settings, get_settings


ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = ROOT / ".auth"
AUTH_STATE_PATH = AUTH_DIR / "aster_session.json"


def parse_persist_state(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        state = json.loads(raw)
    except Exception:
        return {}

    parsed: dict[str, Any] = {}
    for key, value in state.items():
        if isinstance(value, str):
            try:
                parsed[key] = json.loads(value)
            except Exception:
                parsed[key] = value
        else:
            parsed[key] = value
    return parsed


def has_auth_tokens(raw: str | None) -> bool:
    state = parse_persist_state(raw)
    return bool(state.get("authorizationToken") and state.get("companyToken"))


async def save_current_aster_session(page: Page, path: Path = AUTH_STATE_PATH) -> dict[str, Any]:
    session = await page.evaluate(
        """() => ({
          url: location.href,
          origin: location.origin,
          localStorage: Object.fromEntries(Object.entries(localStorage)),
          sessionStorage: Object.fromEntries(Object.entries(sessionStorage)),
        })"""
    )

    raw_persist = session.get("sessionStorage", {}).get("persist:SPS_AHS")
    session["hasAsterAuthTokens"] = has_auth_tokens(raw_persist)
    session["savedAt"] = datetime.now(timezone.utc).isoformat()

    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    return session


async def restore_aster_session(page: Page, path: Path = AUTH_STATE_PATH) -> bool:
    if not path.exists():
        return False

    state = json.loads(path.read_text(encoding="utf-8"))
    local_storage = state.get("localStorage", {})
    session_storage = state.get("sessionStorage", {})

    payload = json.dumps(
        {"localStorageData": local_storage, "sessionStorageData": session_storage},
        ensure_ascii=False,
    )
    script = """(() => {
          const { localStorageData, sessionStorageData } = __ASTER_STORAGE_PAYLOAD__;
          for (const [key, value] of Object.entries(localStorageData || {})) {
            window.localStorage.setItem(key, value)
          }
          for (const [key, value] of Object.entries(sessionStorageData || {})) {
            window.sessionStorage.setItem(key, value)
          }
        })()""".replace("__ASTER_STORAGE_PAYLOAD__", payload)
    await page.add_init_script(script)
    return True


async def manual_login(settings: Settings | None = None, timeout_seconds: int = 600) -> dict[str, Any]:
    settings = settings or get_settings()
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, slow_mo=250)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)
        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")

        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_state: dict[str, Any] = {}
        while asyncio.get_running_loop().time() < deadline:
            last_state = await save_current_aster_session(page)
            if last_state.get("hasAsterAuthTokens"):
                await context.close()
                await browser.close()
                return {
                    "saved": True,
                    "hasAsterAuthTokens": True,
                    "path": str(AUTH_STATE_PATH.relative_to(ROOT)),
                    "url": last_state.get("url"),
                }
            await page.wait_for_timeout(2_000)

        await context.close()
        await browser.close()
        return {
            "saved": True,
            "hasAsterAuthTokens": bool(last_state.get("hasAsterAuthTokens")),
            "path": str(AUTH_STATE_PATH.relative_to(ROOT)),
            "url": last_state.get("url"),
            "warning": "Manual login timeout reached before authorization/company tokens appeared.",
        }


def main() -> None:
    print(json.dumps(asyncio.run(manual_login()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
