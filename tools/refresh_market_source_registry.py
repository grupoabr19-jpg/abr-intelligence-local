from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_market_database, load_env


DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "ABR-Intelligence/1.0"


@dataclass(frozen=True)
class SourceDefinition:
    source_key: str
    source_name: str
    source_type: str
    category: str
    frequency: str
    env_keys: tuple[str, ...]
    default_url: str
    docs_url: str | None = None
    health_kind: str = "http"
    metadata: dict[str, Any] | None = None


SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        "bcb_dolar_ptax",
        "BCB dolar PTAX",
        "api",
        "macro",
        "diaria",
        ("BCB_DOLAR_API_BASE_URL",),
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata",
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/documentacao",
        "bcb_ptax",
    ),
    SourceDefinition(
        "ibge_pim_sidra",
        "IBGE PIM SIDRA",
        "api",
        "industria",
        "mensal",
        ("IBGE_SIDRA_VALUES_BASE_URL", "IBGE_SIDRA_DESCRIPTOR_BASE_URL", "IBGE_PIM_TABLE_ID", "IBGE_PIM_DEFAULT_PATH"),
        "https://apisidra.ibge.gov.br/values",
        "https://apisidra.ibge.gov.br/DescritoresTabela/t",
        "ibge_descriptor",
        {"table_env": "IBGE_PIM_TABLE_ID", "default_table": "8888"},
    ),
    SourceDefinition(
        "ibge_construcao_sidra",
        "IBGE construcao SIDRA",
        "api",
        "construcao",
        "mensal",
        (
            "IBGE_SIDRA_VALUES_BASE_URL",
            "IBGE_SIDRA_DESCRIPTOR_BASE_URL",
            "IBGE_CONSTRUCTION_TABLE_ID",
            "IBGE_CONSTRUCTION_DEFAULT_PATH",
        ),
        "https://apisidra.ibge.gov.br/values",
        "https://apisidra.ibge.gov.br/DescritoresTabela/t",
        "ibge_descriptor",
        {"table_env": "IBGE_CONSTRUCTION_TABLE_ID", "default_table": "8886"},
    ),
    SourceDefinition(
        "aneel_dados_abertos",
        "ANEEL dados abertos",
        "api",
        "energia",
        "mensal",
        ("ANEEL_API_BASE_URL", "ANEEL_PARQUET_BASE_URL", "ANEEL_API_TOKEN"),
        "https://dadosabertos.aneel.gov.br",
        None,
        "aneel",
    ),
    SourceDefinition(
        "comex_stat_ncm",
        "Comex Stat NCM",
        "api",
        "comercio_exterior",
        "mensal",
        ("COMEX_STAT_API_BASE_URL", "COMEX_STAT_CSV_BASE_URL", "COMEX_STAT_API_TOKEN"),
        "https://api-comexstat.mdic.gov.br",
        None,
        "comex",
    ),
    SourceDefinition(
        "aco_brasil_estatistica_mensal",
        "Aco Brasil estatistica mensal",
        "html",
        "aco",
        "mensal",
        ("ACO_BRASIL_DOWNLOAD_URL", "ACO_BRASIL_PAGE_URL"),
        "https://www.acobrasil.org.br/site/estatistica-mensal/",
        None,
        "html_contains",
        {"tokens": ["xlsx", "xls", "estatistica"]},
    ),
    SourceDefinition(
        "cni_sondagem_industrial",
        "CNI sondagem industrial",
        "html",
        "industria",
        "mensal",
        ("CNI_INDUSTRIA_PAGE_URL",),
        "https://www.portaldaindustria.com.br/estatisticas/sondagem-industrial/",
        None,
        "html_contains",
        {"tokens": ["serie", "recente", "sondagem"]},
    ),
    SourceDefinition(
        "cni_sondagem_construcao",
        "CNI sondagem industria da construcao",
        "html",
        "construcao",
        "mensal",
        ("CNI_CONSTRUCAO_PAGE_URL",),
        "https://www.portaldaindustria.com.br/estatisticas/sondagem-industria-da-construcao/",
        None,
        "html_contains",
        {"tokens": ["serie", "recente", "construcao"]},
    ),
    SourceDefinition(
        "inda_estatisticas",
        "INDA estatisticas",
        "html",
        "aco",
        "mensal",
        ("INDA_HTML_URL", "INDA_PAGE_URL"),
        "https://www.inda.org.br/estatisticas/",
        None,
        "html_contains",
        {"tokens": ["compras", "vendas", "estoque", "importacao"]},
    ),
    SourceDefinition(
        "caged_microdados",
        "CAGED microdados",
        "ftp",
        "trabalho",
        "mensal",
        ("CAGED_MICRODADOS_BASE_URL",),
        "ftp://ftp.mtps.gov.br/pdet/microdados/",
        None,
        "ftp",
    ),
    SourceDefinition(
        "pncp_consulta",
        "PNCP consulta",
        "api",
        "governo",
        "diaria",
        ("PNCP_API_BASE_URL",),
        "https://pncp.gov.br/api/consulta/v1",
        "https://pncp.gov.br/api/consulta/swagger-ui/index.html?configUrl=/pncp-api/v3/api-docs/swagger-config",
        "pncp",
    ),
    SourceDefinition(
        "world_bank_wdi",
        "World Bank WDI",
        "api",
        "macro",
        "anual",
        ("WORLD_BANK_API_BASE_URL", "WORLD_BANK_COUNTRIES", "WORLD_BANK_INDICATORS", "WORLD_BANK_START_YEAR"),
        "https://api.worldbank.org/v2",
        "https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures",
        "world_bank",
    ),
    SourceDefinition(
        "obrasgov_projetos",
        "ObrasGov projetos",
        "api",
        "governo",
        "diaria",
        ("OBRASGOV_API_BASE_URL", "OBRASGOV_YEARS", "OBRASGOV_PAGE_SIZE", "OBRASGOV_MAX_PAGES"),
        "https://api-publica.obrasgov.gestao.gov.br/obras",
        "https://api-publica.obrasgov.gestao.gov.br/obras/docs",
        "obrasgov",
    ),
)


def clean_url(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("[") and "](" in value and value.endswith(")"):
        value = value.split("](", 1)[1][:-1]
    return value


def resolve_url(env: dict[str, str], source: SourceDefinition) -> tuple[str, bool]:
    for key in source.env_keys:
        value = clean_url(env.get(key, ""))
        if value and not key.endswith("_TOKEN"):
            return value, True
    return source.default_url, bool(source.default_url)


def http_ok(client: httpx.Client, url: str) -> tuple[bool, dict[str, Any], str | None]:
    response = client.get(url)
    metadata = {"status_code": response.status_code, "content_type": response.headers.get("content-type")}
    if response.status_code >= 400:
        return False, metadata, f"HTTP {response.status_code}"
    metadata["bytes"] = len(response.content)
    return True, metadata, None


def check_bcb(client: httpx.Client, base_url: str) -> tuple[bool, dict[str, Any], str | None]:
    end = date.today()
    start = end - timedelta(days=10)
    url = (
        f"{base_url.rstrip('/')}/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        f"?@dataInicial='{start:%m-%d-%Y}'&@dataFinalCotacao='{end:%m-%d-%Y}'&$top=5&$format=json"
    )
    ok, metadata, error = http_ok(client, url)
    if not ok:
        return ok, metadata, error
    data = client.get(url).json()
    values = data.get("value", [])
    metadata["records_seen"] = len(values)
    metadata["probe_url"] = url
    return bool(values), metadata, None if values else "Nenhuma cotacao retornada no periodo de teste."


def check_ibge_descriptor(client: httpx.Client, env: dict[str, str], source: SourceDefinition) -> tuple[bool, dict[str, Any], str | None]:
    table_env = (source.metadata or {}).get("table_env")
    table_id = env.get(table_env or "") or (source.metadata or {}).get("default_table")
    descriptor_base = env.get("IBGE_SIDRA_DESCRIPTOR_BASE_URL") or "https://apisidra.ibge.gov.br/DescritoresTabela/t"
    url = f"{descriptor_base.rstrip('/')}/{quote(str(table_id))}"
    ok, metadata, error = http_ok(client, url)
    metadata["table_id"] = table_id
    metadata["probe_url"] = url
    return ok, metadata, error


def check_aneel(client: httpx.Client, base_url: str) -> tuple[bool, dict[str, Any], str | None]:
    url = f"{base_url.rstrip('/')}/api/3/action/package_search?q=distribuida&rows=1"
    return http_ok(client, url)


def check_comex(client: httpx.Client, base_url: str) -> tuple[bool, dict[str, Any], str | None]:
    base = base_url.rstrip("/")
    if "api-comexstat" in base:
        url = f"{base}/general/dates/updated"
        return http_ok(client, url)
    year = date.today().year
    url = f"{base}/IMP_{year}.csv"
    try:
        response = client.head(url)
    except httpx.ConnectError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        with httpx.Client(timeout=60, follow_redirects=True, verify=False) as fallback_client:
            response = fallback_client.head(url)
        metadata = {"tls_verify_fallback": True}
    else:
        metadata = {}
    if response.status_code == 405:
        response = client.get(url, headers={"range": "bytes=0-2048"})
    metadata.update({"status_code": response.status_code, "probe_url": url})
    if response.status_code >= 400:
        return False, metadata, f"HTTP {response.status_code}"
    return True, metadata, None


def check_html_contains(client: httpx.Client, source: SourceDefinition, url: str) -> tuple[bool, dict[str, Any], str | None]:
    try:
        response = client.get(url)
    except httpx.ReadTimeout:
        try:
            response = client.get(url, timeout=45.0)
        except httpx.ReadTimeout:
            head_response = client.head(url, timeout=30.0)
            metadata = {
                "status_code": head_response.status_code,
                "content_type": head_response.headers.get("content-type"),
                "probe_url": url,
                "probe_method": "HEAD_AFTER_GET_TIMEOUT",
            }
            if head_response.status_code < 400:
                return True, metadata, None
            return False, metadata, f"HTTP {head_response.status_code}"
    metadata = {"status_code": response.status_code, "content_type": response.headers.get("content-type"), "probe_url": url}
    if response.status_code >= 400:
        return False, metadata, f"HTTP {response.status_code}"
    text = response.text.lower()
    tokens = [str(item).lower() for item in (source.metadata or {}).get("tokens", [])]
    found = [token for token in tokens if token in text]
    metadata["tokens_found"] = found
    metadata["bytes"] = len(response.content)
    return bool(found), metadata, None if found else "Pagina acessivel, mas os marcadores esperados nao foram encontrados."


def check_ftp(url: str, timeout: int) -> tuple[bool, dict[str, Any], str | None]:
    request = Request(url)
    with urlopen(request, timeout=timeout) as response:
        chunk = response.read(2048)
    return bool(chunk), {"bytes_sampled": len(chunk), "probe_url": url}, None


def check_pncp(client: httpx.Client, base_url: str) -> tuple[bool, dict[str, Any], str | None]:
    today = date.today()
    normalized_base_url = base_url.rstrip("/")
    if "/swagger-ui" in normalized_base_url or "/api-docs" in normalized_base_url:
        normalized_base_url = "https://pncp.gov.br/api/consulta/v1"
    url = f"{normalized_base_url}/contratacoes/publicacao"
    params = {
        "dataInicial": today.strftime("%Y%m%d"),
        "dataFinal": today.strftime("%Y%m%d"),
        "codigoModalidadeContratacao": "6",
        "pagina": 1,
        "tamanhoPagina": 10,
    }
    response = client.get(url, params=params)
    metadata = {"status_code": response.status_code, "probe_url": str(response.url)}
    if response.status_code == 400:
        metadata["note"] = "Endpoint respondeu 400 para data sem publicacao; a API esta acessivel."
        return True, metadata, None
    if response.status_code >= 400:
        return False, metadata, f"HTTP {response.status_code}"
    return True, metadata, None


def check_world_bank(client: httpx.Client, base_url: str) -> tuple[bool, dict[str, Any], str | None]:
    url = f"{base_url.rstrip('/')}/country/BRA/indicator/NY.GDP.MKTP.KD.ZG"
    response = client.get(url, params={"format": "json", "per_page": 1})
    metadata = {"status_code": response.status_code, "probe_url": str(response.url)}
    if response.status_code >= 400:
        return False, metadata, f"HTTP {response.status_code}"
    payload = response.json()
    records = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
    metadata["records_seen"] = len(records)
    return bool(records), metadata, None if records else "World Bank nao retornou registros no probe."


def check_obrasgov(client: httpx.Client, base_url: str) -> tuple[bool, dict[str, Any], str | None]:
    url = f"{base_url.rstrip('/')}/projeto-investimento"
    response = client.get(url, params={"pagina": 1, "tamanho_da_pagina": 1})
    metadata = {"status_code": response.status_code, "probe_url": str(response.url)}
    if response.status_code >= 400:
        return False, metadata, f"HTTP {response.status_code}"
    payload = response.json()
    records = payload.get("data") if isinstance(payload, dict) else []
    metadata["records_seen"] = len(records or [])
    metadata["total_items"] = payload.get("total_items") if isinstance(payload, dict) else None
    return bool(records), metadata, None if records else "ObrasGov nao retornou registros no probe."


def source_health(env: dict[str, str], client: httpx.Client, source: SourceDefinition) -> tuple[bool, bool, str, dict[str, Any], str | None]:
    url, configured = resolve_url(env, source)
    if not configured:
        return False, False, "DISABLED", {}, None
    try:
        if source.health_kind == "bcb_ptax":
            reachable, metadata, error = check_bcb(client, url)
        elif source.health_kind == "ibge_descriptor":
            reachable, metadata, error = check_ibge_descriptor(client, env, source)
        elif source.health_kind == "aneel":
            reachable, metadata, error = check_aneel(client, url)
        elif source.health_kind == "comex":
            reachable, metadata, error = check_comex(client, url)
        elif source.health_kind == "html_contains":
            reachable, metadata, error = check_html_contains(client, source, url)
        elif source.health_kind == "ftp":
            timeout = int(env.get("EXTERNAL_DATA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
            reachable, metadata, error = check_ftp(url, timeout)
        elif source.health_kind == "pncp":
            reachable, metadata, error = check_pncp(client, url)
        elif source.health_kind == "world_bank":
            reachable, metadata, error = check_world_bank(client, url)
        elif source.health_kind == "obrasgov":
            reachable, metadata, error = check_obrasgov(client, url)
        else:
            reachable, metadata, error = http_ok(client, url)
    except Exception as exc:
        return configured, False, "ERROR", {"base_url": url}, f"{type(exc).__name__}: {exc}"
    status = "CONFIGURED" if reachable else "ERROR"
    metadata["base_url"] = url
    return configured, reachable, status, metadata, error


def latest_source_state(cur: Any, source_key: str) -> dict[str, Any]:
    cur.execute(
        """
        select max(finalizado_em),
               coalesce(sum(registros_inseridos), 0)
        from public.mercado_coletas
        where source_key = %s and status = 'sucesso'
        """,
        (source_key,),
    )
    success_at, collected_rows = cur.fetchone()
    cur.execute(
        """
        select max(coalesce(periodo_label, to_char(periodo_inicio, 'YYYY-MM'))),
               count(*)
        from public.mercado_indicadores
        where source_key = %s
        """,
        (source_key,),
    )
    latest_period, indicator_rows = cur.fetchone()
    return {
        "last_success_at": success_at,
        "latest_reference_period": latest_period,
        "last_row_count": int(indicator_rows or collected_rows or 0),
    }


def final_status(source: SourceDefinition, configured: bool, reachable: bool, probe_status: str, state: dict[str, Any]) -> str:
    if not configured:
        return "DISABLED"
    if not reachable:
        return "ERROR"
    if not state["last_row_count"]:
        return "CONFIGURED"
    last_success_at = state.get("last_success_at")
    if not last_success_at:
        return "HEALTHY"
    days = (datetime.now(timezone.utc) - last_success_at).days
    max_age = 3 if source.frequency == "diaria" else 45
    return "STALE" if days > max_age else "HEALTHY"


def refresh_registry(dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    timeout = int(env.get("EXTERNAL_DATA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
    headers = {"user-agent": env.get("EXTERNAL_DATA_USER_AGENT") or DEFAULT_USER_AGENT}
    result: dict[str, Any] = {"sources": []}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        with connect_market_database(env) as conn:
            with conn.cursor() as cur:
                for source in SOURCES:
                    configured, reachable, probe_status, metadata, error = source_health(env, client, source)
                    state = latest_source_state(cur, source.source_key)
                    status = final_status(source, configured, reachable, probe_status, state)
                    base_url, _ = resolve_url(env, source)
                    payload = {
                        "source_key": source.source_key,
                        "source_name": source.source_name,
                        "status": status,
                        "configured": configured,
                        "reachable": reachable,
                        "latest_reference_period": state["latest_reference_period"],
                        "last_row_count": state["last_row_count"],
                        "error_message": error,
                    }
                    result["sources"].append(payload)
                    if dry_run:
                        continue
                    cur.execute(
                        """
                        insert into public.market_source_registry(
                          source_key, source_name, source_type, category, frequency, configured,
                          reachable, status, base_url, docs_url, env_keys, last_success_at,
                          latest_reference_period, last_row_count, error_message, metadata,
                          checked_at, updated_at
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                                %s, %s, %s, %s::jsonb, now(), now())
                        on conflict (source_key)
                        do update set
                          source_name = excluded.source_name,
                          source_type = excluded.source_type,
                          category = excluded.category,
                          frequency = excluded.frequency,
                          configured = excluded.configured,
                          reachable = excluded.reachable,
                          status = excluded.status,
                          base_url = excluded.base_url,
                          docs_url = excluded.docs_url,
                          env_keys = excluded.env_keys,
                          last_success_at = excluded.last_success_at,
                          latest_reference_period = excluded.latest_reference_period,
                          last_row_count = excluded.last_row_count,
                          error_message = excluded.error_message,
                          metadata = excluded.metadata,
                          checked_at = now(),
                          updated_at = now()
                        """,
                        (
                            source.source_key,
                            source.source_name,
                            source.source_type,
                            source.category,
                            source.frequency,
                            configured,
                            reachable,
                            status,
                            base_url,
                            source.docs_url,
                            json.dumps(source.env_keys),
                            state["last_success_at"],
                            state["latest_reference_period"],
                            state["last_row_count"],
                            error,
                            json.dumps(metadata, ensure_ascii=False),
                        ),
                    )
                if not dry_run:
                    conn.commit()
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Atualiza registro operacional das fontes de mercado.")
    parser.add_argument("--dry-run", action="store_true", help="Executa validacoes sem gravar no banco.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = refresh_registry(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
