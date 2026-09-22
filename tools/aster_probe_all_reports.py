from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import Request, Response, async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.browser_capture import try_login
from backend.aster_collector.manual_auth import has_auth_tokens, save_current_aster_session
from backend.aster_collector.settings import get_settings


EVIDENCE_DIR = ROOT / "docs" / "evidence"
CATALOG_PATH = EVIDENCE_DIR / "aster_report_catalog.json"
OUTPUT_JSON = EVIDENCE_DIR / "aster_report_contracts.json"
OUTPUT_MD = EVIDENCE_DIR / "aster_report_contracts.md"


def report_id_from_route(route: str | None) -> str | None:
    if not route or not route.startswith("ExecuteReport/"):
        return None
    return route.split("/", 1)[1]


def classify_report(report: dict[str, Any]) -> str:
    text = " ".join(
        str(report.get(key) or "")
        for key in ("name", "route", "description", "path")
    ).lower()
    if any(token in text for token in ("estoque", "inventory", "produto", "wms")):
        return "estoque"
    if any(token in text for token in ("contas a receber", "inadimpl", "finance", "receber")):
        return "financeiro"
    if any(token in text for token in ("venda", "comercial", "cliente", "lead", "indica")):
        return "comercial_clientes"
    if any(token in text for token in ("transport", "ocorr", "materiais em transito")):
        return "transporte"
    if any(token in text for token in ("produção", "producao", "estrutura")):
        return "producao"
    return "outros"


async def wait_for_login(page, timeout_seconds: int = 180) -> None:
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


async def response_json(response: Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        return None
    try:
        return await response.json()
    except Exception:
        return None


async def main_async() -> dict[str, Any]:
    settings = get_settings()
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    reports = [
        report
        for report in catalog.get("reports", [])
        if report_id_from_route(report.get("route"))
    ]

    contracts: dict[str, dict[str, Any]] = {}
    active_report_id: str | None = None

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.headless, slow_mo=100)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(settings.browser_timeout_ms)

        async def on_response(response: Response) -> None:
            nonlocal active_report_id
            request: Request = response.request
            url = response.url
            if not active_report_id or f"/APP/CRM/ReportQueries/{active_report_id}/" not in url:
                return
            body = await response_json(response)
            item = contracts.setdefault(active_report_id, {})
            item.setdefault("events", []).append(
                {
                    "method": request.method,
                    "url": url,
                    "status": response.status,
                    "contentType": response.headers.get("content-type", ""),
                }
            )
            if url.endswith("/parameters"):
                item["parameters"] = body
            elif url.endswith("/settings"):
                item["settings"] = body
            elif url.endswith("/check_permission"):
                item["check_permission_status"] = response.status

        page.on("response", lambda response: asyncio.create_task(on_response(response)))

        await page.goto(str(settings.aster_base_url), wait_until="domcontentloaded")
        await wait_for_login(page)

        for report in reports:
            report_id = report_id_from_route(report.get("route"))
            if not report_id:
                continue
            active_report_id = report_id
            contracts.setdefault(report_id, {})
            contracts[report_id]["report"] = report
            contracts[report_id]["area"] = classify_report(report)
            await page.goto(f"https://aster.gruposps.com.br/ExecuteReport/{report_id}", wait_until="domcontentloaded")
            await page.wait_for_timeout(5_000)

        await context.close()
        await browser.close()

    result = {
        "report_count": len(reports),
        "contract_count": len(contracts),
        "contracts": [
            {"query_id": query_id, **contract}
            for query_id, contract in sorted(contracts.items())
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result)
    return result


def write_markdown(result: dict[str, Any]) -> None:
    lines = [
        "# Aster Report Contracts",
        "",
        f"Reports probed: `{result['report_count']}`",
        f"Contracts found: `{result['contract_count']}`",
        "",
    ]
    by_area: dict[str, list[dict[str, Any]]] = {}
    for contract in result["contracts"]:
        by_area.setdefault(contract.get("area") or "outros", []).append(contract)

    for area, contracts in sorted(by_area.items()):
        lines.extend([f"## {area}", ""])
        for contract in contracts:
            report = contract.get("report") or {}
            params = (contract.get("parameters") or {}).get("parameters") or []
            status = ",".join(str(event.get("status")) for event in contract.get("events", []))
            lines.append(f"- `{contract['query_id']}` {report.get('path') or report.get('name')} status=[{status}]")
            for param in params:
                req = " required" if param.get("required") else ""
                lines.append(f"  - `{param.get('name')}` {param.get('label')} ({param.get('type')}{req})")
        lines.append("")

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    result = asyncio.run(main_async())
    print(
        json.dumps(
            {
                "report_count": result["report_count"],
                "contract_count": result["contract_count"],
                "output_json": str(OUTPUT_JSON.relative_to(ROOT)),
                "output_md": str(OUTPUT_MD.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
