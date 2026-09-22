from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.aster_collector.report_registry import REPORTS


EVIDENCE_DIR = ROOT / "docs" / "evidence"
CONTRACTS_PATH = EVIDENCE_DIR / "aster_report_contracts.json"
OUTPUT_JSON = EVIDENCE_DIR / "aster_training_matrix.json"
OUTPUT_MD = ROOT / "docs" / "aster-training-matrix.md"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_summary(query_id: str) -> dict[str, Any]:
    return load_json(EVIDENCE_DIR / f"aster_live_ingest_summary_{query_id}.json")


def load_probe(query_id: str) -> dict[str, Any]:
    return load_json(EVIDENCE_DIR / f"aster_form_probe_{query_id}.json")


def contract_by_id() -> dict[str, dict[str, Any]]:
    contracts = load_json(CONTRACTS_PATH).get("contracts") or []
    return {contract["query_id"]: contract for contract in contracts}


def summarize_config(query_id: str) -> dict[str, Any]:
    config = REPORTS[query_id]
    summary = load_summary(query_id)
    probe = load_probe(query_id)
    contract = contract_by_id().get(query_id, {})
    params = ((contract.get("parameters") or {}).get("parameters") or [])

    return {
        "query_id": query_id,
        "area": config.area,
        "name": config.name,
        "entity": config.entity,
        "status": config.automation_status,
        "notes": config.notes,
        "params": [
            {
                "name": param.get("name"),
                "label": param.get("label"),
                "type": param.get("type"),
                "required": bool(param.get("required")),
            }
            for param in params
        ],
        "static_fields": [field.__dict__ for field in config.static_fields],
        "text_fields": [field.__dict__ for field in config.text_fields],
        "date_fields": [field.__dict__ for field in config.date_fields],
        "last_summary": {
            "sync_id": summary.get("sync_id"),
            "rows_captured": summary.get("rows_captured"),
            "columns_count": summary.get("columns_count"),
            "filters": summary.get("filters"),
        }
        if summary
        else None,
        "last_probe": {
            "url": probe.get("url"),
            "inputs": len(probe.get("inputs") or []),
            "buttons": len(probe.get("buttons") or []),
        }
        if probe
        else None,
    }


def write_markdown(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Matriz de Treinamento Aster",
        "",
        "Esta matriz e gerada a partir dos contratos capturados, do registro operacional do robo e das evidencias de execucao/probe.",
        "",
        "| Area | Query ID | Relatorio | Status | Ultima leitura | Observacao |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        last = row.get("last_summary") or {}
        last_text = "-"
        if last.get("sync_id"):
            last_text = f"{last.get('rows_captured')} linhas; {last.get('sync_id')}"
        notes = (row.get("notes") or "").replace("|", "/")
        lines.append(
            f"| {row['area']} | `{row['query_id']}` | {row['name']} | {row['status']} | {last_text} | {notes} |"
        )

    lines.extend(
        [
            "",
            "## Regras Aprendidas",
            "",
            "- `D0A4D301`: `Tipo` vazio representa todos; `Filial` deve ser selecionada como `Todos` pelo dropdown.",
            "- `0F75E84D`: datas simples nas posicoes 0 e 1.",
            "- `37D9E431`: fora da prioridade atual; contas a receber nao deve guiar o treino principal.",
            "- Vendas do `D0A4D301` sao classificadas por varejo/atacado e regiao com `backend/aster_collector/commercial_regions.py`.",
            "- Relatorios de estoque com `FAMILIA` exigem permissao e/ou queryField; `804C04C1` retornou `PageNotAuthorized` no probe atual.",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = [summarize_config(query_id) for query_id in sorted(REPORTS)]
    result = {"reports": rows}
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(rows)
    print(
        json.dumps(
            {
                "reports": len(rows),
                "output_json": str(OUTPUT_JSON.relative_to(ROOT)),
                "output_md": str(OUTPUT_MD.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
