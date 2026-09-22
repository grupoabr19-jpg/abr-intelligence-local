from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from backend.aster_collector.commercial_regions import classify_sale
from backend.aster_collector.report_registry import REPORTS
from tools.apply_migrations import connect_database, load_env
from tools.summarize_aster_sales_regions import parse_decimal


def list_reports() -> list[dict[str, str]]:
    return [
        {
            "query_id": query_id,
            "area": report.area,
            "name": report.name,
            "entity": report.entity,
            "automation_status": report.automation_status,
            "notes": report.notes,
        }
        for query_id, report in sorted(REPORTS.items())
    ]


def sales_regions_summary() -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"linhas": 0, "valor_total": Decimal("0"), "criterios": defaultdict(int)}
    )
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select payload_original
                from public.staging_dados
                where entidade = 'aster_report_d0a4d301'
                """
            )
            rows = [row[0] for row in cur.fetchall()]

    for payload in rows:
        classification = classify_sale(
            city=payload.get("Cidade"),
            seller=payload.get("Vendedor"),
            segment=payload.get("Segmento"),
        )
        key = (classification.canal, classification.regiao or "sem_regiao")
        groups[key]["linhas"] += 1
        groups[key]["valor_total"] += parse_decimal(payload.get("Valor Total"))
        groups[key]["criterios"][classification.criterio] += 1

    return [
        {
            "canal": canal,
            "regiao": regiao,
            "linhas": data["linhas"],
            "valor_total": f"{data['valor_total']:.2f}",
            "criterios": dict(data["criterios"]),
        }
        for (canal, regiao), data in sorted(groups.items())
    ]
