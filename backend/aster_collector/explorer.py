from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page, async_playwright

from .browser_capture import looks_like_data_response, try_login
from .settings import Settings, get_settings


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "docs" / "evidence"

DENY_TEXT = (
    "excluir",
    "deletar",
    "delete",
    "remover",
    "salvar",
    "save",
    "gravar",
    "confirmar",
    "cancelar",
    "enviar",
    "submit",
    "logout",
    "sair",
)

REPORT_HINTS = (
    "relat",
    "report",
    "dashboard",
    "venda",
    "pedido",
    "estoque",
    "cliente",
    "produto",
    "margem",
    "fatur",
    "compr",
    "produção",
    "producao",
)


@dataclass
class ExplorationState:
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    login_status: str | None = None
    pages: list[dict[str, Any]] = field(default_factory=list)
    network: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def clean_text(text: str | None, limit: int = 160) -> str:
    return " ".join((text or "").split())[:limit]


def is_safe_candidate(text: str) -> bool:
    lowered = text.lower()
    return bool(text) and not any(deny in lowered for deny in DENY_TEXT)


async def snapshot_page(page: Page, label: str) -> dict[str, Any]:
    return await page.evaluate(
        """({ label }) => {
          const visibleText = (el) => {
            const style = window.getComputedStyle(el)
            const rect = el.getBoundingClientRect()
            return style.visibility !== 'hidden' &&
              style.display !== 'none' &&
              rect.width > 0 &&
              rect.height > 0
          }
          const pick = (el, index) => ({
            index,
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute('role') || '',
            type: el.getAttribute('type') || '',
            href: el.href || '',
            id: el.id || '',
            name: el.getAttribute('name') || '',
            aria: el.getAttribute('aria-label') || '',
            title: el.getAttribute('title') || '',
            text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 180),
          })
          const selector = [
            'a',
            'button',
            '[role="button"]',
            '[role="menuitem"]',
            '[role="link"]',
            '[aria-label]',
            '[title]',
            '[onclick]'
          ].join(',')
          return {
            label,
            url: location.href,
            title: document.title,
            bodyText: (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 3000),
            candidates: [...document.querySelectorAll(selector)].filter(visibleText).slice(0, 250).map(pick),
          }
        }""",
        {"label": label},
    )


async def click_candidate(page: Page, candidate: dict[str, Any]) -> bool:
    text = clean_text(candidate.get("text") or candidate.get("aria") or candidate.get("title"))
    if not is_safe_candidate(text):
        return False

    selectors: list[str] = []
    if candidate.get("id"):
        selectors.append(f"#{candidate['id']}")
    if candidate.get("aria"):
        selectors.append(f"[aria-label={json.dumps(candidate['aria'])}]")
    if candidate.get("title"):
        selectors.append(f"[title={json.dumps(candidate['title'])}]")

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.click(timeout=4_000)
                await page.wait_for_load_state("networkidle", timeout=12_000)
                return True
        except Exception:
            continue

    try:
        locator = page.get_by_text(text, exact=True).first
        if await locator.count() > 0:
            await locator.click(timeout=4_000)
            await page.wait_for_load_state("networkidle", timeout=12_000)
            return True
    except Exception:
        return False

    return False


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        text = clean_text(candidate.get("text") or candidate.get("aria") or candidate.get("title"))
        lowered = text.lower()
        if not is_safe_candidate(text):
            continue
        score = 0
        if any(hint in lowered for hint in REPORT_HINTS):
            score += 100
        if candidate.get("tag") in {"a", "button"}:
            score += 10
        if candidate.get("role") in {"button", "menuitem", "link"}:
            score += 10
        score += min(len(text), 80)
        if score > 20:
            scored.append((score, candidate))
    return [candidate for _, candidate in sorted(scored, key=lambda item: item[0], reverse=True)]


async def explore_aster(max_clicks: int = 30, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    state = ExplorationState()
    seen_urls: set[str] = set()
    clicked_texts: set[str] = set()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.headless)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)

        async def on_response(response):
            try:
                content_type = response.headers.get("content-type", "")
                if not looks_like_data_response(response.url, content_type):
                    return
                state.network.append(
                    {
                        "url": response.url,
                        "status": response.status,
                        "content_type": content_type,
                        "method": response.request.method,
                        "resource_type": response.request.resource_type,
                    }
                )
            except Exception as exc:
                state.errors.append(f"network: {type(exc).__name__}: {exc}")

        page.on("response", on_response)

        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        state.login_status = await try_login(page, settings)
        await page.wait_for_timeout(3_000)

        first = await snapshot_page(page, "initial")
        state.pages.append(first)
        seen_urls.add(first["url"])

        queue = rank_candidates(first["candidates"])
        clicks = 0

        while queue and clicks < max_clicks:
            candidate = queue.pop(0)
            text = clean_text(candidate.get("text") or candidate.get("aria") or candidate.get("title"))
            if text in clicked_texts:
                continue
            clicked_texts.add(text)

            before_url = page.url
            clicked = await click_candidate(page, candidate)
            if not clicked:
                continue

            clicks += 1
            await page.wait_for_timeout(1_500)
            label = f"click_{clicks}_{text[:60]}"
            snap = await snapshot_page(page, label)
            snap["clicked"] = {
                "text": text,
                "tag": candidate.get("tag"),
                "role": candidate.get("role"),
                "href": candidate.get("href"),
            }
            state.pages.append(snap)

            if snap["url"] not in seen_urls:
                seen_urls.add(snap["url"])
                queue.extend(rank_candidates(snap["candidates"]))

            if page.url != before_url:
                try:
                    await page.go_back(wait_until="networkidle", timeout=12_000)
                    await page.wait_for_timeout(1_000)
                except Exception:
                    pass

        await context.close()
        await browser.close()

    result = {
        "started_at": state.started_at,
        "login_status": state.login_status,
        "page_count": len(state.pages),
        "network_count": len(state.network),
        "pages": state.pages,
        "network": state.network,
        "errors": state.errors,
    }

    (EVIDENCE_DIR / "aster_exploration.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown_summary(result)
    return result


def write_markdown_summary(result: dict[str, Any]) -> None:
    lines = [
        "# Aster Exploration",
        "",
        f"Started at: `{result['started_at']}`",
        f"Login status: `{result['login_status']}`",
        f"Pages inspected: `{result['page_count']}`",
        f"Network calls captured: `{result['network_count']}`",
        "",
        "## Pages",
    ]

    for page in result["pages"]:
        lines.append("")
        lines.append(f"### {page['label']}")
        lines.append(f"- URL: `{page['url']}`")
        lines.append(f"- Title: `{page['title']}`")
        if page.get("clicked"):
            lines.append(f"- Clicked: `{page['clicked']['text']}`")
        body = clean_text(page.get("bodyText"), 500)
        if body:
            lines.append(f"- Text sample: {body}")
        candidates = [
            clean_text(c.get("text") or c.get("aria") or c.get("title"))
            for c in page.get("candidates", [])
        ]
        candidates = [c for c in candidates if c][:20]
        if candidates:
            lines.append("- Candidates:")
            for candidate in candidates:
                lines.append(f"  - {candidate}")

    lines.append("")
    lines.append("## Network")
    seen = set()
    for item in result["network"]:
        key = (item["method"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- `{item['method']}` `{item['status']}` {item['url']}")

    if result["errors"]:
        lines.append("")
        lines.append("## Errors")
        for error in result["errors"]:
            lines.append(f"- {error}")

    (EVIDENCE_DIR / "aster_exploration.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    result = asyncio.run(explore_aster())
    print(
        json.dumps(
            {
                "login_status": result["login_status"],
                "page_count": result["page_count"],
                "network_count": result["network_count"],
                "output_json": "docs/evidence/aster_exploration.json",
                "output_md": "docs/evidence/aster_exploration.md",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
