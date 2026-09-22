from __future__ import annotations

import asyncio
from typing import Any, Literal

import httpx
from playwright.async_api import Page, async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from .settings import Settings, get_settings


def looks_like_data_response(url: str, content_type: str) -> bool:
    lowered = url.lower()
    if any(lowered.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff", ".woff2")):
        return False
    return "json" in content_type.lower() or any(token in lowered for token in ("api", "report", "query", "data", "execute"))


def find_largest_object_array(value: Any, best: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    best = best or []
    if isinstance(value, list):
        objects = [item for item in value if isinstance(item, dict)]
        if len(objects) > len(best):
            best = objects
        for item in value[:20]:
            best = find_largest_object_array(item, best)
    elif isinstance(value, dict):
        for item in value.values():
            best = find_largest_object_array(item, best)
    return best


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def send_rows(settings: Settings, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    if not settings.abr_ingest_url or not settings.abr_collector_key or not settings.abr_aster_fonte_id:
        return

    payload = {
        "fonte_id": settings.abr_aster_fonte_id,
        "entidade": settings.abr_aster_entidade,
        "rows": rows,
        "metadata": metadata,
    }
    headers = {"x-collector-key": settings.abr_collector_key}

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(settings.abr_ingest_url, json=payload, headers=headers)
        response.raise_for_status()


async def attach_network_capture(page: Page, settings: Settings) -> None:
    async def on_response(response):
        try:
            content_type = response.headers.get("content-type", "")
            if not looks_like_data_response(response.url, content_type):
                return

            data = await response.json()
            rows = find_largest_object_array(data)[:1000]
            if not rows:
                return

            await send_rows(
                settings,
                rows,
                {
                    "endpoint": response.url,
                    "status": response.status,
                    "content_type": content_type,
                },
            )
        except Exception:
            # Network capture must never break the operator navigation.
            return

    page.on("response", on_response)


async def try_login(page: Page, settings: Settings) -> Literal["logged_in", "login_submitted", "login_form_not_found"]:
    email_candidates = page.locator(
        "input[type='email'], input[name*='email' i], input[id*='email' i], input[name*='login' i], input[id*='login' i], input[type='text']",
    )
    password_candidates = page.locator("input[type='password']")

    if await email_candidates.count() == 0 or await password_candidates.count() == 0:
        return "login_form_not_found"

    email = email_candidates.first
    password = password_candidates.first

    await email.fill(settings.aster_login_email)
    await password.fill(settings.aster_login_password)

    submit = page.locator("button[type='submit'], button:has-text('Entrar'), button:has-text('Login'), input[type='submit']").first
    if await submit.count() > 0:
        await submit.click()
    else:
        await password.press("Enter")

    await page.wait_for_load_state("networkidle")
    return "login_submitted"


async def run_aster_session(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.aster_login_email or not settings.aster_login_password:
        raise RuntimeError("Configure ASTER_LOGIN_EMAIL and ASTER_LOGIN_PASSWORD in the environment.")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.headless)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)

        await attach_network_capture(page, settings)
        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        login_status = await try_login(page, settings)
        await page.wait_for_timeout(5000)

        result = {
            "url": page.url,
            "title": await page.title(),
            "login_status": login_status,
        }

        if not settings.headless:
            await page.pause()

        await context.close()
        await browser.close()
        return result


def main() -> None:
    print(asyncio.run(run_aster_session()))


if __name__ == "__main__":
    main()
