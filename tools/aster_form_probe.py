from __future__ import annotations

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.browser_capture import try_login
from backend.aster_collector.manual_auth import has_auth_tokens, save_current_aster_session
from backend.aster_collector.settings import get_settings


EVIDENCE_DIR = ROOT / "docs" / "evidence"


async def wait_for_login(page, timeout_seconds: int = 120) -> None:
    settings = get_settings()
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        session = await save_current_aster_session(page)
        raw_persist = session.get("sessionStorage", {}).get("persist:SPS_AHS")
        if has_auth_tokens(raw_persist):
            return
        if settings.aster_login_email and settings.aster_login_password:
            try:
                await try_login(page, settings)
            except Exception:
                pass
        await page.wait_for_timeout(2_000)
    raise SystemExit("Timeout aguardando login Aster.")


async def main_async(query_id: str) -> dict[str, Any]:
    settings = get_settings()
    target_url = f"https://aster.gruposps.com.br/ExecuteReport/{query_id}"
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)
        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        await wait_for_login(page)
        await page.goto(target_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5_000)
        data = await page.evaluate(
            """() => {
              const brief = (el) => ({
                tag: el.tagName,
                text: (el.innerText || el.textContent || '').trim().slice(0, 120),
                id: el.id || null,
                name: el.getAttribute('name'),
                type: el.getAttribute('type'),
                role: el.getAttribute('role'),
                aria: el.getAttribute('aria-label'),
                placeholder: el.getAttribute('placeholder'),
                cls: el.className ? String(el.className).slice(0, 200) : null,
                value: el.value ?? null,
                rect: (() => {
                  const r = el.getBoundingClientRect()
                  return { x: r.x, y: r.y, w: r.width, h: r.height }
                })(),
              })
              return {
                url: location.href,
                inputs: Array.from(document.querySelectorAll('input, textarea, select')).map(brief),
                buttons: Array.from(document.querySelectorAll('button, [role=button]')).map(brief),
                rightPanelText: Array.from(document.querySelectorAll('body *'))
                  .filter(el => {
                    const r = el.getBoundingClientRect()
                    return r.x > window.innerWidth * 0.65 && r.width > 20 && r.height > 5
                  })
                  .slice(0, 120)
                  .map(brief),
              }
            }"""
        )
        await context.close()
        await browser.close()
    output = EVIDENCE_DIR / f"aster_form_probe_{query_id}.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id", default="D0A4D301")
    args = parser.parse_args()
    query_id = args.query_id.upper()
    result = asyncio.run(main_async(query_id))
    print(
        json.dumps(
            {
                "url": result.get("url"),
                "inputs": len(result.get("inputs", [])),
                "buttons": len(result.get("buttons", [])),
                "output_json": f"docs/evidence/aster_form_probe_{query_id}.json",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
