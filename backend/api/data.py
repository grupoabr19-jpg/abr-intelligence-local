from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from backend.aster_collector.commercial_regions import classify_sale
from backend.aster_collector.data_requirements import EXTRACTION_RULES, REQUIREMENTS, requirements_by_source
from backend.aster_collector.external_sources import EXTERNAL_SPREADSHEET_SOURCES
from backend.aster_collector.report_registry import REPORTS
from backend.intelligence_domains import list_intelligence_domains
from tools.apply_migrations import connect_database, load_env
from tools.summarize_aster_sales_regions import parse_decimal


def list_reports() -> list[dict[str, Any]]:
    requirements_index = requirements_by_source()
    return [
        {
            "query_id": query_id,
            "area": report.area,
            "name": report.name,
            "entity": report.entity,
            "automation_status": report.automation_status,
            "deliverables": [item.key for item in requirements_index.get(query_id, ())],
            "notes": report.notes,
        }
        for query_id, report in sorted(REPORTS.items())
    ]


def list_requirements() -> dict[str, Any]:
    return {
        "requirements": [
            {
                "key": item.key,
                "title": item.title,
                "priority": item.priority,
                "refresh": item.refresh,
                "grain": item.grain,
                "objective": item.objective,
                "fields": list(item.fields),
                "known_sources": list(item.known_sources),
                "gaps": list(item.gaps),
            }
            for item in REQUIREMENTS
        ],
        "external_spreadsheet_sources": [
            {
                "key": item.key,
                "title": item.title,
                "folder_url": item.folder_url,
                "selection_rule": item.selection_rule,
                "latest_file_id": item.latest_file_id,
                "latest_file_name": item.latest_file_name,
                "latest_modified_time": item.latest_modified_time,
                "local_path": item.local_path,
                "likely_coverage": list(item.likely_coverage),
                "notes": item.notes,
            }
            for item in EXTERNAL_SPREADSHEET_SOURCES
        ],
        "extraction_rules": list(EXTRACTION_RULES),
    }


def list_domains() -> dict[str, Any]:
    return {"domains": list_intelligence_domains()}


def internal_dashboard_summary() -> dict[str, Any]:
    reports = list_reports()
    requirements = list_requirements()
    warnings: list[str] = []

    status_counts: dict[str, int] = defaultdict(int)
    area_counts: dict[str, int] = defaultdict(int)
    for report in reports:
        status_counts[report["automation_status"]] += 1
        area_counts[report["area"]] += 1

    requirement_rows = requirements["requirements"]
    covered_requirements = [item for item in requirement_rows if item["known_sources"]]
    gap_requirements = [item for item in requirement_rows if item["gaps"]]

    history: list[dict[str, Any]] = []
    staging_by_entity: list[dict[str, Any]] = []
    try:
        env = load_env()
        with connect_database(env) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select entidade, sync_id, status, registros_lidos, registros_inseridos, iniciado_em
                    from public.historico_importacoes
                    order by iniciado_em desc
                    limit 12
                    """
                )
                history = [
                    {
                        "entidade": row[0],
                        "sync_id": row[1],
                        "status": row[2],
                        "registros_lidos": row[3],
                        "registros_inseridos": row[4],
                        "iniciado_em": row[5].isoformat() if row[5] else None,
                    }
                    for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    select entidade, count(*)::int
                    from public.staging_dados
                    group by entidade
                    order by count(*) desc
                    limit 12
                    """
                )
                staging_by_entity = [
                    {"entidade": row[0], "linhas": row[1]}
                    for row in cur.fetchall()
                ]
    except BaseException as exc:
        warnings.append(f"Banco indisponivel para resumo ao vivo: {type(exc).__name__}: {str(exc)[:160]}")

    regions: list[dict[str, Any]] = []
    try:
        regions = sales_regions_summary()
    except BaseException as exc:
        warnings.append(f"Resumo de regioes indisponivel: {type(exc).__name__}: {str(exc)[:160]}")

    return {
        "domain": "internal",
        "generated_from": "backend",
        "kpis": {
            "reports_total": len(reports),
            "reports_validated": status_counts.get("validated", 0),
            "reports_empty": status_counts.get("validated_empty", 0),
            "requirements_total": len(requirement_rows),
            "requirements_covered": len(covered_requirements),
            "requirements_with_gaps": len(gap_requirements),
            "spreadsheet_sources": len(requirements["external_spreadsheet_sources"]),
            "history_events": len(history),
        },
        "reports": reports,
        "reports_by_status": [{"status": key, "total": value} for key, value in sorted(status_counts.items())],
        "reports_by_area": [{"area": key, "total": value} for key, value in sorted(area_counts.items())],
        "requirements": requirement_rows,
        "external_spreadsheet_sources": requirements["external_spreadsheet_sources"],
        "staging_by_entity": staging_by_entity,
        "recent_history": history,
        "sales_regions": regions,
        "warnings": warnings,
    }


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
