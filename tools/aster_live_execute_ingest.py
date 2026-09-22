from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Request, Response, async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.manual_auth import has_auth_tokens, save_current_aster_session
from backend.aster_collector.browser_capture import try_login
from backend.aster_collector.report_registry import DateFieldBinding, StaticFieldBinding, TextFieldBinding, get_report_config
from backend.aster_collector.settings import get_settings


EVIDENCE_DIR = ROOT / "docs" / "evidence"
DEFAULT_QUERY_ID = "D0A4D301"
DEFAULT_DATE_FROM = "2026-09-01"
DEFAULT_DATE_TO = "2026-09-30"


def to_br_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def post_ingest(env: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        env["ABR_INGEST_URL"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "x-collector-key": env["ABR_COLLECTOR_KEY"],
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"status": response.status, "body": json.loads(body)}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"status": exc.code, "body": body}


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


async def ensure_login(page, settings, timeout_seconds: int) -> dict[str, Any]:
    session = await wait_for_login(page, 8)
    if session.get("hasAsterAuthTokens"):
        return session

    if settings.aster_login_email and settings.aster_login_password:
        await try_login(page, settings)
        return await wait_for_login(page, timeout_seconds)

    return await wait_for_login(page, timeout_seconds)


async def fill_date_by_label(page, label_text: str, value: str) -> bool:
    label = page.get_by_text(label_text, exact=False).first
    if await label.count() == 0:
        return False

    try:
        container = label.locator(
            "xpath=ancestor::*[self::label or self::div or self::section or self::fieldset][1]"
        )
        field = container.locator("input").first
        if await field.count() > 0:
            await field.fill(value)
            await field.press("Tab")
            return True
    except Exception:
        return False
    return False


async def visible_right_inputs(page) -> list[dict[str, Any]]:
    return await page.locator("input").evaluate_all(
        """(inputs) => inputs
          .map((input, index) => {
            const r = input.getBoundingClientRect()
            const style = window.getComputedStyle(input)
            return {
              index,
              x: r.x,
              y: r.y,
              w: r.width,
              h: r.height,
              visible: style.visibility !== 'hidden' && style.display !== 'none'
            }
          })
          .filter(item => item.visible && item.x > window.innerWidth * 0.55 && item.w > 40 && item.h > 20)
          .sort((a, b) => a.y - b.y)"""
    )


async def wait_for_report_inputs(page, minimum_count: int, timeout_ms: int = 45_000) -> list[dict[str, Any]]:
    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
    last_seen: list[dict[str, Any]] = []
    while asyncio.get_running_loop().time() < deadline:
        last_seen = await visible_right_inputs(page)
        if len(last_seen) >= minimum_count:
            return last_seen
        await page.wait_for_timeout(500)
    return last_seen


async def set_input_value(page, input_index: int, value: str) -> None:
    field = page.locator("input").nth(input_index)
    await field.evaluate(
        """(input, value) => {
          input.focus()
          input.value = value
          input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }))
          input.dispatchEvent(new Event('change', { bubbles: true }))
          input.blur()
        }""",
        value,
    )


async def choose_dropdown_value(page, input_index: int, value: str) -> str:
    field = page.locator("input").nth(input_index)
    await field.click()
    await page.wait_for_timeout(300)
    await field.press("Control+A")
    await field.type(value, delay=30)
    await page.wait_for_timeout(700)

    clicked = await page.evaluate(
        """(value) => {
          const isVisible = (element) => {
            const rect = element.getBoundingClientRect()
            const style = window.getComputedStyle(element)
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
          }
          const candidates = Array.from(document.querySelectorAll('li, div, span, button, [role="option"]'))
            .filter((element) => isVisible(element) && (element.innerText || element.textContent || '').trim() === value)
          const option = candidates[candidates.length - 1]
          if (!option) return false
          option.click()
          return true
        }""",
        value,
    )
    if clicked:
        await page.wait_for_timeout(300)
        return "option_click"

    await field.press("Enter")
    await page.wait_for_timeout(300)
    return "enter"


async def fill_report_filters(
    page,
    date_from: str,
    date_to: str,
    static_fields: tuple[StaticFieldBinding, ...],
    text_fields: tuple[TextFieldBinding, ...],
    date_fields: tuple[DateFieldBinding, ...],
) -> dict[str, Any]:
    date_from_ui = to_br_date(date_from)
    date_to_ui = to_br_date(date_to)
    result = {"date_from": date_from, "date_to": date_to, "filled": []}
    if not static_fields and not text_fields and not date_fields:
        result["message"] = "Relatorio sem campos configurados."
        return result

    try:
        all_positions = (
            [field.input_position for field in static_fields]
            + [field.input_position for field in text_fields]
            + [field.input_position for field in date_fields]
        )
        minimum_count = max(all_positions) + 1
        right_inputs = await wait_for_report_inputs(page, minimum_count)
        if len(right_inputs) >= minimum_count:
            for binding in text_fields:
                field_index = right_inputs[binding.input_position]["index"]
                await set_input_value(page, field_index, binding.value)
                result["filled"].append(f"{binding.name}:right_input[{field_index}]={binding.value}")

            for binding in static_fields:
                field_index = right_inputs[binding.input_position]["index"]
                method = await choose_dropdown_value(page, field_index, binding.value)
                result["filled"].append(f"{binding.name}:right_input[{field_index}]={binding.value}:{method}")

            values = [date_from_ui, date_to_ui]
            for binding, field_value in zip(date_fields, values):
                field_index = right_inputs[binding.input_position]["index"]
                await set_input_value(page, field_index, field_value)
                result["filled"].append(f"{binding.name}:right_input[{field_index}]")
            return result
        result["right_panel_input_count"] = len(right_inputs)
    except Exception as exc:
        result["right_panel_error"] = f"{type(exc).__name__}: {exc}"

    if await fill_date_by_label(page, "Data de", date_from_ui):
        result["filled"].append("Data de")
    if await fill_date_by_label(page, "Data até", date_to_ui) or await fill_date_by_label(page, "Data ate", date_to_ui):
        result["filled"].append("Data ate")

    # Fallback for masked inputs that are not reachable through label containers.
    if len(result["filled"]) < 2:
        inputs = page.locator("input")
        count = await inputs.count()
        date_values = [date_from_ui, date_to_ui]
        filled_indexes = []
        for index in range(min(count, 20)):
            if len(filled_indexes) >= 2:
                break
            field = inputs.nth(index)
            try:
                input_type = (await field.get_attribute("type") or "").lower()
                value = await field.input_value()
                placeholder = await field.get_attribute("placeholder") or ""
                if input_type in ("date", "text") and (
                    "data" in placeholder.lower()
                    or "/" in value
                    or "-" in value
                    or input_type == "date"
                ):
                    await field.fill(date_values[len(filled_indexes)])
                    await field.press("Tab")
                    filled_indexes.append(index)
            except Exception:
                continue
        if filled_indexes:
            result["filled"].append(f"fallback_inputs={filled_indexes}")

    return result


async def click_execute_button(page) -> str | None:
    candidates = [
        "Executar",
        "Gerar",
        "Gerar relatório",
        "Gerar relatorio",
        "Visualizar",
        "Confirmar",
        "Aplicar",
        "Pesquisar",
        "OK",
    ]
    for text in candidates:
        button = page.get_by_role("button", name=text, exact=False).first
        try:
            if await button.count() > 0 and await button.is_visible():
                await button.click()
                return text
        except Exception:
            continue

    for text in candidates:
        clickable = page.get_by_text(text, exact=False).first
        try:
            if await clickable.count() > 0 and await clickable.is_visible():
                await clickable.click()
                return text
        except Exception:
            continue

    clicked = await page.evaluate(
        """(labels) => {
          const isVisible = (element) => {
            const rect = element.getBoundingClientRect()
            const style = window.getComputedStyle(element)
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
          }
          const elements = Array.from(document.querySelectorAll('button, [role="button"]'))
          for (const label of labels) {
            const element = elements.find((candidate) => isVisible(candidate) && (candidate.innerText || '').includes(label))
            if (element) {
              element.click()
              return label
            }
          }
          return null
        }""",
        candidates,
    )
    if clicked:
        return str(clicked)
    return None


async def capture_execute(
    query_id: str,
    timeout_seconds: int,
    *,
    auto_execute: bool,
    date_from: str,
    date_to: str,
) -> dict[str, Any]:
    settings = get_settings()
    report_config = get_report_config(query_id)
    target_url = f"https://aster.gruposps.com.br/ExecuteReport/{query_id}"
    captured: dict[str, Any] = {}
    event_count = 0

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, slow_mo=150)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)

        async def on_response(response: Response) -> None:
            nonlocal captured, event_count
            request: Request = response.request
            url = response.url
            if f"/APP/CRM/ReportQueries/{query_id}/" not in url:
                return
            event_count += 1
            if not url.endswith("/execute") or request.method != "POST" or not (200 <= response.status < 300):
                return
            try:
                body = await response.json()
            except Exception as exc:
                captured = {"error": f"Falha ao ler JSON do /execute: {type(exc).__name__}: {exc}"}
                return
            captured = {
                "status": response.status,
                "url": url,
                "postData": request.post_data_json,
                "body": body,
            }

        page.on("response", lambda response: asyncio.create_task(on_response(response)))

        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        session = await ensure_login(page, settings, timeout_seconds)
        if not session.get("hasAsterAuthTokens"):
            await context.close()
            await browser.close()
            raise SystemExit("Timeout antes de detectar tokens do Aster.")

        await page.goto(target_url, wait_until="domcontentloaded")
        automation: dict[str, Any] = {
            "auto_execute": auto_execute,
            "date_from": date_from,
            "date_to": date_to,
            "report_name": report_config.name,
            "automation_status": report_config.automation_status,
            "fill_result": None,
            "clicked": None,
        }
        if auto_execute:
            automation["fill_result"] = await fill_report_filters(
                page,
                date_from,
                date_to,
                report_config.static_fields,
                report_config.text_fields,
                report_config.date_fields,
            )
            await page.wait_for_timeout(500)
            automation["clicked"] = await click_execute_button(page)
            if not automation["clicked"]:
                print("Nao encontrei automaticamente o botao de executar; aguardando intervencao manual.")
        else:
            print()
            print("Aster aberto. Preencha filtros e clique no botao de gerar/executar relatorio.")
            print("Quando um POST /execute 2xx for capturado, os dados serao ingeridos sem salvar dataset bruto.")
            print()

        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline and not captured:
            await page.wait_for_timeout(1_000)

        final_url = page.url
        if not captured:
            screenshot = EVIDENCE_DIR / f"aster_live_ingest_timeout_{query_id}.png"
            await page.screenshot(path=str(screenshot), full_page=True)
            await context.close()
            await browser.close()
            raise SystemExit(
                json.dumps(
                    {
                        "error": "Nenhum /execute 2xx capturado dentro do timeout.",
                        "event_count": event_count,
                        "timeout_screenshot": str(screenshot.relative_to(ROOT)),
                        "automation": automation,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

        captured["final_url"] = final_url
        captured["event_count"] = event_count
        captured["automation"] = automation
        await context.close()
        await browser.close()
        return captured


async def main_async(
    query_id: str,
    timeout_seconds: int,
    *,
    auto_execute: bool,
    date_from: str,
    date_to: str,
) -> dict[str, Any]:
    env = load_env()
    required = ("ABR_INGEST_URL", "ABR_COLLECTOR_KEY", "ABR_ASTER_FONTE_ID")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise SystemExit("Variaveis ausentes: " + ", ".join(missing))

    execute = await capture_execute(
        query_id=query_id,
        timeout_seconds=timeout_seconds,
        auto_execute=auto_execute,
        date_from=date_from,
        date_to=date_to,
    )
    report_config = get_report_config(query_id)
    body = execute.get("body") or {}
    rows = body.get("data") or []
    if not isinstance(rows, list) or not rows:
        raise SystemExit("O /execute 2xx nao retornou linhas em body.data.")

    sync_id = f"ASTER-{query_id}-{int(time.time())}"
    columns = body.get("columns") or []
    post_params = (execute.get("postData") or {}).get("params") or {}
    metadata = {
        "query_id": query_id,
        "report_area": report_config.area,
        "report_name": report_config.name,
        "filters": post_params,
        "automation": execute.get("automation"),
        "columns": columns,
        "captured_rows": len(rows),
        "final_url": execute.get("final_url"),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "ingestion_mode": "live_execute_memory",
    }

    responses = []
    for index, batch in enumerate(chunks(rows, 1000), start=1):
        payload = {
            "fonte_id": env["ABR_ASTER_FONTE_ID"],
            "sync_id": sync_id,
            "entidade": report_config.entity,
            "rows": batch,
            "metadata": {**metadata, "batch_index": index, "batch_rows": len(batch)},
        }
        result = post_ingest(env, payload)
        responses.append(result)
        if result["status"] < 200 or result["status"] >= 300:
            raise SystemExit(json.dumps({"sync_id": sync_id, "failed": result}, ensure_ascii=False, indent=2))

    summary = {
        "sync_id": sync_id,
        "query_id": query_id,
        "rows_captured": len(rows),
        "batch_count": len(responses),
        "responses": responses,
        "columns_count": len(columns),
        "filters": post_params,
        "automation": execute.get("automation"),
    }
    output = EVIDENCE_DIR / f"aster_live_ingest_summary_{query_id}.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**summary, "output_json": str(output.relative_to(ROOT))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id", default=DEFAULT_QUERY_ID)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", default=DEFAULT_DATE_TO)
    parser.add_argument("--manual", action="store_true", help="Nao tenta preencher/clicar automaticamente.")
    args = parser.parse_args()
    result = asyncio.run(
        main_async(
            query_id=args.query_id,
            timeout_seconds=args.timeout_seconds,
            auto_execute=not args.manual,
            date_from=args.date_from,
            date_to=args.date_to,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
