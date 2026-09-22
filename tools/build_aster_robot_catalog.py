from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence"
TERMS = (
    "report",
    "relat",
    "execute",
    "consulta",
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


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def relevant(values: list[str]) -> list[str]:
    return [value for value in values if any(term in value.lower() for term in TERMS)]


def main() -> None:
    static = load_json(EVIDENCE_DIR / "aster_static_analysis.json", {})
    exploration = load_json(EVIDENCE_DIR / "aster_exploration.json", {"network": []})

    catalog = {
        "status": "seed_from_static_bundle_and_initial_network",
        "static_bundle": static.get("bundles", []),
        "priority_routes": relevant(static.get("routes", []))[:200],
        "priority_endpoints": relevant(static.get("endpoints", []))[:200],
        "priority_labels": relevant(static.get("labels", []))[:200],
        "observed_initial_network": exploration.get("network", []),
        "needs_authenticated_menu": True,
        "notes": [
            "Authenticated probe did not obtain authorizationToken/companyToken yet; menu/report inventory still needs a valid authenticated session or corrected login selectors.",
        ],
    }

    (EVIDENCE_DIR / "aster_robot_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Aster Robot Catalog",
        "",
        f"Status: `{catalog['status']}`",
        "",
        "## Priority Routes",
        *[f"- `{item}`" for item in catalog["priority_routes"][:80]],
        "",
        "## Priority Endpoints",
        *[f"- `{item}`" for item in catalog["priority_endpoints"][:120]],
        "",
        "## Priority Labels",
        *[f"- {item}" for item in catalog["priority_labels"][:80]],
        "",
        "## Observed Initial Network",
    ]

    for item in catalog["observed_initial_network"]:
        lines.append(f"- `{item.get('method')}` `{item.get('status')}` {item.get('url')}")

    lines.extend(
        [
            "",
            "## Next Authenticated Step",
            "- Obter `authorizationToken` e `companyToken` validos pelo login real ou por modo manual assistido.",
            "- Consultar `/main_menu/user` para listar todos os modulos liberados.",
            "- Consultar `APP/CRM/ReportQueries` e `/ReportQueries` com os headers reais.",
            "- Para cada relatorio, identificar `reportCode`, parametros obrigatorios e endpoint de execucao/download.",
        ]
    )

    (EVIDENCE_DIR / "aster_robot_catalog.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "routes": len(catalog["priority_routes"]),
                "endpoints": len(catalog["priority_endpoints"]),
                "labels": len(catalog["priority_labels"]),
                "output": "docs/evidence/aster_robot_catalog.md",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
