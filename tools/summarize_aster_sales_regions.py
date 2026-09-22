from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.commercial_regions import classify_sale
from tools.apply_migrations import connect_database, load_env


OUTPUT_JSON = ROOT / "docs" / "evidence" / "aster_sales_regions_summary.json"
OUTPUT_MD = ROOT / "docs" / "evidence" / "aster_sales_regions_summary.md"


def parse_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip()
    if not text:
        return Decimal("0")
    text = re.sub(r"[^0-9,.-]", "", text)
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def money(value: Decimal) -> str:
    return f"{value:.2f}"


def main() -> None:
    env = load_env()
    groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"linhas": 0, "valor_total": Decimal("0"), "criterios": defaultdict(int)}
    )
    examples: list[dict[str, Any]] = []

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
        group = groups[key]
        group["linhas"] += 1
        group["valor_total"] += parse_decimal(payload.get("Valor Total"))
        group["criterios"][classification.criterio] += 1
        if len(examples) < 25:
            examples.append(
                {
                    "cidade": payload.get("Cidade"),
                    "vendedor": payload.get("Vendedor"),
                    "segmento": payload.get("Segmento"),
                    "canal": classification.canal,
                    "regiao": classification.regiao,
                    "criterio": classification.criterio,
                }
            )

    result_rows = []
    for (canal, regiao), data in sorted(groups.items()):
        result_rows.append(
            {
                "canal": canal,
                "regiao": regiao,
                "linhas": data["linhas"],
                "valor_total": money(data["valor_total"]),
                "criterios": dict(data["criterios"]),
            }
        )

    result = {"grupos": result_rows, "exemplos": examples}
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Resumo de Vendas por Canal e Regiao",
        "",
        "Fonte: staging `aster_report_d0a4d301` classificada pelo mapa de atendimento de varejo/atacado.",
        "",
        "| Canal | Regiao | Linhas | Valor Total | Criterios |",
        "|---|---|---:|---:|---|",
    ]
    for row in result_rows:
        lines.append(
            f"| {row['canal']} | {row['regiao']} | {row['linhas']} | {row['valor_total']} | {row['criterios']} |"
        )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"grupos": len(result_rows), "output_json": str(OUTPUT_JSON.relative_to(ROOT)), "output_md": str(OUTPUT_MD.relative_to(ROOT))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
