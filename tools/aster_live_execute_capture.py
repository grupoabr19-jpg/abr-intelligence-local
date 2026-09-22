from __future__ import annotations

import asyncio
import argparse
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
DEFAULT_QUERY_ID = "D0A4D301"
SENSITIVE_HEADER_PARTS = ("authorization", "token", "cookie", "password", "sktid")


def redact_headers(headers: dict[str, str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in sorted(headers.items()):
        key_lower = key.lower()
        if any(part in key_lower for part in SENSITIVE_HEADER_PARTS):
            output[key] = {"redacted": True, "length": len(value or "")}
        else:
            output[key] = value
    return output


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
        return [sanitize_json(item) for item in value[:200]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "...[truncated]"
    return value


def summarize_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: summarize_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return {
            "type": "list",
            "length": len(value),
            "sample": summarize_shape(value[0]) if value else None,
        }
    return type(value).__name__


async def response_json(response: Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        return None
    try:
        return await response.json()
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


async def main_async(query_id: str = DEFAULT_QUERY_ID, timeout_seconds: int = 600) -> dict[str, Any]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    target_url = f"https://aster.gruposps.com.br/ExecuteReport/{query_id}"
    execute_events: list[dict[str, Any]] = []
    successful_execute_events: list[dict[str, Any]] = []
    all_report_events: list[dict[str, Any]] = []
    aster_posts: list[dict[str, Any]] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, slow_mo=150)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)

        async def on_response(response: Response) -> None:
            request: Request = response.request
            url = response.url
            if "astersrv.gruposps.com.br" in url and request.method == "POST":
                aster_posts.append(
                    {
                        "method": request.method,
                        "url": url,
                        "status": response.status,
                        "requestHeaders": redact_headers(await request.all_headers()),
                        "postData": sanitize_json(request.post_data_json),
                        "responseContentType": response.headers.get("content-type", ""),
                    }
                )
            if f"/APP/CRM/ReportQueries/{query_id}/" not in url:
                return

            raw_body = await response_json(response)
            item = {
                "method": request.method,
                "url": url,
                "status": response.status,
                "requestHeaders": redact_headers(await request.all_headers()),
                "postData": sanitize_json(request.post_data_json if request.method == "POST" else None),
                "responseContentType": response.headers.get("content-type", ""),
                "responseShape": summarize_shape(raw_body),
                "responsePreview": sanitize_json(raw_body),
            }
            all_report_events.append(item)
            if url.endswith("/execute"):
                execute_events.append(item)
                if 200 <= response.status < 300:
                    successful_execute_events.append(item)

        page.on("response", lambda response: asyncio.create_task(on_response(response)))

        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        session = await wait_for_login(page, timeout_seconds)
        if not session.get("hasAsterAuthTokens"):
            await context.close()
            await browser.close()
            return {
                "query_id": query_id,
                "hasAsterAuthTokens": False,
                "warning": "Timeout antes de detectar tokens do Aster.",
                "execute_event_count": 0,
                "events": all_report_events,
            }

        await page.goto(target_url, wait_until="domcontentloaded")
        print()
        print("Aster aberto. Preencha os filtros e clique no botao que executa/gera o relatorio.")
        print("Dica: use um periodo curto, como 7 a 30 dias.")
        print("O capturador vai encerrar automaticamente quando observar um POST /execute com status 2xx.")
        print()

        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline and not successful_execute_events:
            await page.wait_for_timeout(1_000)

        screenshot_path = None
        if not successful_execute_events:
            screenshot_path = EVIDENCE_DIR / f"aster_execute_timeout_{query_id}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)

        result = {
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "query_id": query_id,
            "target": target_url,
            "final_url": page.url,
            "hasAsterAuthTokens": True,
            "execute_event_count": len(execute_events),
            "successful_execute_event_count": len(successful_execute_events),
            "report_event_count": len(all_report_events),
            "aster_post_count": len(aster_posts),
            "events": all_report_events,
            "aster_posts": aster_posts,
            "timeout_screenshot": str(screenshot_path.relative_to(ROOT)) if screenshot_path else None,
            "warning": None
            if successful_execute_events
            else "Nenhum /execute 2xx capturado dentro do timeout.",
        }

        await context.close()
        await browser.close()

    output_json = EVIDENCE_DIR / f"aster_execute_capture_{query_id}.json"
    output_md = EVIDENCE_DIR / f"aster_execute_capture_{query_id}.md"
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, output_md)
    return result


def write_markdown(result: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Aster Execute Capture",
        "",
        f"Query ID: `{result.get('query_id')}`",
        f"Target: `{result.get('target')}`",
        f"Final URL: `{result.get('final_url')}`",
        f"Execute events: `{result.get('execute_event_count')}`",
        f"Successful execute events: `{result.get('successful_execute_event_count')}`",
        f"Aster POST events: `{result.get('aster_post_count')}`",
        f"Timeout screenshot: `{result.get('timeout_screenshot')}`",
        f"Warning: `{result.get('warning')}`",
        "",
        "## Report Query Events",
    ]
    for item in result.get("events", []):
        lines.append(f"- `{item['status']}` `{item['method']}` {item['url']}")
        lines.append(f"  - shape: `{json.dumps(item.get('responseShape'), ensure_ascii=False)}`")
    lines.extend(["", "## All Aster POSTs"])
    for item in result.get("aster_posts", []):
        lines.append(f"- `{item['status']}` `{item['method']}` {item['url']}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id", default=DEFAULT_QUERY_ID)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    result = asyncio.run(main_async(query_id=args.query_id, timeout_seconds=args.timeout_seconds))
    print(
        json.dumps(
            {
                "query_id": result.get("query_id"),
                "execute_event_count": result.get("execute_event_count"),
                "successful_execute_event_count": result.get("successful_execute_event_count"),
                "report_event_count": result.get("report_event_count"),
                "aster_post_count": result.get("aster_post_count"),
                "timeout_screenshot": result.get("timeout_screenshot"),
                "warning": result.get("warning"),
                "output_json": f"docs/evidence/aster_execute_capture_{result.get('query_id')}.json",
                "output_md": f"docs/evidence/aster_execute_capture_{result.get('query_id')}.md",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
