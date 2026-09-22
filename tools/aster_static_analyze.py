from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "docs" / "evidence"
ASTER_URL = "https://aster.gruposps.com.br/Login/abr"


def unique_sorted(values: set[str]) -> list[str]:
    return sorted(values, key=lambda value: (value.lower(), value))


def main() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=90, follow_redirects=True, trust_env=False) as client:
        html = client.get(ASTER_URL).text
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
        bundle_urls = [
            urljoin(ASTER_URL, src)
            for src in scripts
            if "assets/" in src and src.endswith(".js")
        ]

        bundles: list[dict[str, object]] = []
        all_text = ""
        for url in bundle_urls:
            text = client.get(url).text
            all_text += "\n" + text
            path = EVIDENCE_DIR / f"aster_bundle_{Path(url).name}"
            path.write_text(text, encoding="utf-8")
            bundles.append({"url": url, "bytes": len(text), "path": str(path.relative_to(ROOT))})

    string_literals = set(re.findall(r'["\']([^"\']{3,180})["\']', all_text))

    endpoints = {
        value
        for value in string_literals
        if (
            value.startswith("/")
            or "astersrv.gruposps.com.br" in value
            or re.match(r"^[A-Za-z][A-Za-z0-9_/-]{2,}$", value)
        )
        and any(token in value.lower() for token in ("report", "relat", "execute", "dashboard", "company", "user", "pedido", "venda", "estoque", "token", "auth"))
    }

    labels = {
        value
        for value in string_literals
        if any(token in value.lower() for token in ("relat", "report", "administra", "compras", "estoque", "crm", "vendas", "transporte", "parceiro", "execute"))
        and not value.startswith("http")
        and len(value) <= 120
    }

    routes = {
        value
        for value in string_literals
        if value.startswith("/")
        and len(value) <= 140
        and not value.startswith("//")
    }

    result = {
        "source": ASTER_URL,
        "scripts": scripts,
        "bundles": bundles,
        "routes": unique_sorted(routes),
        "endpoints": unique_sorted(endpoints),
        "labels": unique_sorted(labels),
    }

    (EVIDENCE_DIR / "aster_static_analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Aster Static Analysis",
        "",
        f"Source: `{ASTER_URL}`",
        "",
        "## Bundles",
        *[f"- `{item['url']}` ({item['bytes']} bytes)" for item in bundles],
        "",
        "## Routes",
        *[f"- `{route}`" for route in result["routes"][:200]],
        "",
        "## Endpoints / Endpoint-like Strings",
        *[f"- `{endpoint}`" for endpoint in result["endpoints"][:250]],
        "",
        "## Labels / Module-like Strings",
        *[f"- {label}" for label in result["labels"][:250]],
    ]
    (EVIDENCE_DIR / "aster_static_analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "bundles": len(bundles),
        "routes": len(result["routes"]),
        "endpoints": len(result["endpoints"]),
        "labels": len(result["labels"]),
        "output_json": "docs/evidence/aster_static_analysis.json",
        "output_md": "docs/evidence/aster_static_analysis.md",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
