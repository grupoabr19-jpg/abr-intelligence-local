from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


DEFAULT_TIMEOUT = 60
DEFAULT_USER_AGENT = "ABR-Intelligence/1.0"
MONTHS = {
    "jan": 1,
    "fev": 2,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "aug": 8,
    "set": 9,
    "sep": 9,
    "out": 10,
    "oct": 10,
    "nov": 11,
    "dez": 12,
    "dec": 12,
}


@dataclass(frozen=True)
class MarketPageSource:
    key: str
    env_url: str
    default_url: str
    name: str


PAGE_SOURCES = {
    "aco_brasil_estatistica_mensal": MarketPageSource(
        key="aco_brasil_estatistica_mensal",
        env_url="ACO_BRASIL_PAGE_URL",
        default_url="https://www.acobrasil.org.br/site/estatistica-mensal/",
        name="Aco Brasil estatistica mensal",
    ),
    "cni_sondagem_industrial": MarketPageSource(
        key="cni_sondagem_industrial",
        env_url="CNI_INDUSTRIA_PAGE_URL",
        default_url="https://www.portaldaindustria.com.br/estatisticas/sondagem-industrial/",
        name="CNI sondagem industrial",
    ),
    "cni_sondagem_construcao": MarketPageSource(
        key="cni_sondagem_construcao",
        env_url="CNI_CONSTRUCAO_PAGE_URL",
        default_url="https://www.portaldaindustria.com.br/estatisticas/sondagem-industria-da-construcao/",
        name="CNI sondagem industria da construcao",
    ),
    "inda_estatisticas": MarketPageSource(
        key="inda_estatisticas",
        env_url="INDA_PAGE_URL",
        default_url="https://www.inda.org.br/estatisticas/",
        name="INDA estatisticas",
    ),
}


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "a" and attrs_dict.get("href"):
            self._current_href = attrs_dict["href"]
            self._current_text = []
        if tag.lower() == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            self.links.append(
                {
                    "href": self._current_href,
                    "text": clean_text(" ".join(self._current_text)),
                }
            )
            self._current_href = None
            self._current_text = []
        if tag.lower() == "title":
            self._in_title = False


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_key(value: Any) -> str:
    text = clean_text(str(value or "")).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def infer_document_type(url: str, text: str) -> str:
    path = urlparse(url).path.lower()
    probe = f"{path} {text.lower()}"
    if ".pdf" in path:
        return "pdf"
    if ".xlsx" in path or ".xls" in path:
        return "planilha"
    if ".csv" in path:
        return "csv"
    if "download" in probe or "baixar" in probe:
        return "download"
    return "link"


def is_relevant_link(url: str, text: str) -> bool:
    probe = f"{url} {text}".lower()
    blocked_tokens = (
        "compliance",
        "codigo-de-conduta",
        "código de compliance",
    )
    if any(token in probe for token in blocked_tokens):
        return False
    file_tokens = (
        ".pdf",
        ".xls",
        ".xlsx",
        ".csv",
    )
    action_tokens = (
        "download",
        "baixar",
    )
    return any(token in probe for token in file_tokens) or any(token in probe for token in action_tokens)


def parse_month_token(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    text = normalize_key(value).split("_")[0]
    return MONTHS.get(text[:3])


def parse_period_start(value: Any, year_hint: int | None = None, month_hint: Any = None) -> str | None:
    if value is None or pd.isna(value):
        if year_hint and month_hint is not None:
            month = parse_month_token(month_hint)
            return f"{year_hint:04d}-{month:02d}-01" if month else None
        return None
    if hasattr(value, "date"):
        date_value = value.date()
        return f"{date_value.year:04d}-{date_value.month:02d}-01"
    if isinstance(value, (int, float)) and year_hint:
        month = parse_month_token(month_hint)
        return f"{year_hint:04d}-{month:02d}-01" if month else None
    text = clean_text(str(value))
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:7] + "-01"
    month = parse_month_token(text)
    if year_hint and month:
        return f"{year_hint:04d}-{month:02d}-01"
    compact = normalize_key(text)
    match = re.match(r"^([a-z]{3})(\d{2})$", compact)
    if match:
        month = MONTHS.get(match.group(1))
        year = 2000 + int(match.group(2))
        return f"{year:04d}-{month:02d}-01" if month else None
    return None


def numeric_value(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(str(value))
    if not text or text in {"-", "--"}:
        return None
    text = re.sub(r"[^0-9,.-]", "", text)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def year_value(value: Any) -> int | None:
    number = numeric_value(value)
    if number is None:
        return None
    year = int(number)
    return year if 1900 <= year <= 2200 else None


def fetch_page(client: httpx.Client, url: str) -> tuple[str, str]:
    response = client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    return response.text, content_type


def collect_page_source(client: httpx.Client, source: MarketPageSource, page_url: str) -> list[dict[str, Any]]:
    html, content_type = fetch_page(client, page_url)
    parser = LinkExtractor()
    parser.feed(html)
    page_title = clean_text(parser.title) or source.name
    documents: list[dict[str, Any]] = [
        {
            "tipo_documento": "pagina",
            "titulo": page_title,
            "url": page_url,
            "payload": {
                "content_type": content_type,
                "html_sha256": sha256_text(html),
                "source_env": source.env_url,
            },
        }
    ]

    seen = {page_url}
    for link in parser.links:
        absolute_url = urljoin(page_url, link["href"])
        if absolute_url in seen or not is_relevant_link(absolute_url, link["text"]):
            continue
        seen.add(absolute_url)
        documents.append(
            {
                "tipo_documento": infer_document_type(absolute_url, link["text"]),
                "titulo": link["text"] or absolute_url,
                "url": absolute_url,
                "payload": {
                    "href_original": link["href"],
                    "texto_link": link["text"],
                    "pagina_origem": page_url,
                },
            }
        )
    return documents


def start_run(cur: Any, source_key: str, metadata: dict[str, Any]) -> str:
    cur.execute(
        """
        insert into public.mercado_coletas(source_key, status, metadados)
        values (%s, 'processando', %s::jsonb)
        returning id
        """,
        (source_key, json.dumps(metadata, ensure_ascii=False)),
    )
    return str(cur.fetchone()[0])


def finish_run(
    cur: Any,
    run_id: str,
    *,
    status: str,
    found: int = 0,
    upserted: int = 0,
    error: str | None = None,
) -> None:
    cur.execute(
        """
        update public.mercado_coletas
        set status = %s,
            finalizado_em = now(),
            registros_encontrados = %s,
            registros_inseridos = %s,
            erro = %s
        where id = %s
        """,
        (status, found, upserted, error, run_id),
    )


def upsert_documents(cur: Any, source_key: str, run_id: str, documents: list[dict[str, Any]]) -> int:
    count = 0
    for item in documents:
        payload = item.get("payload") or {}
        payload["coleta_id"] = run_id
        cur.execute(
            """
            insert into public.mercado_documentos(
              source_key,
              coleta_id,
              tipo_documento,
              titulo,
              url,
              hash_conteudo,
              payload,
              coletado_em
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
            on conflict (source_key, url)
            do update set
              coleta_id = excluded.coleta_id,
              tipo_documento = excluded.tipo_documento,
              titulo = excluded.titulo,
              hash_conteudo = excluded.hash_conteudo,
              payload = excluded.payload,
              coletado_em = now()
            """,
            (
                source_key,
                run_id,
                item["tipo_documento"],
                item.get("titulo"),
                item["url"],
                sha256_text(json.dumps(item, sort_keys=True, ensure_ascii=False)),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        count += 1
    return count


def latest_planilha_documents(cur: Any, source_keys: list[str]) -> list[dict[str, Any]]:
    cur.execute(
        """
        select distinct on (source_key, url)
          id::text,
          source_key,
          tipo_documento,
          titulo,
          url
        from public.mercado_documentos
        where source_key = any(%s)
          and tipo_documento = 'planilha'
        order by source_key, url, coletado_em desc
        """,
        (source_keys,),
    )
    return [
        {
            "id": row[0],
            "source_key": row[1],
            "tipo_documento": row[2],
            "titulo": row[3],
            "url": row[4],
        }
        for row in cur.fetchall()
    ]


def delete_document_indicators(cur: Any, document_id: str) -> None:
    cur.execute("delete from public.mercado_indicadores where documento_id = %s", (document_id,))


def insert_indicators(cur: Any, document: dict[str, Any], indicators: list[dict[str, Any]]) -> int:
    if not indicators:
        return 0
    rows = [
        (
            document["source_key"],
            document["id"],
            item["indicador_key"],
            item["indicador_nome"],
            item.get("periodo_inicio"),
            item.get("periodo_fim"),
            item.get("periodo_label"),
            item.get("geografia", "BR"),
            item.get("unidade"),
            item.get("valor"),
            item.get("valor_texto"),
            json.dumps(item.get("dimensoes", {}), ensure_ascii=False),
            json.dumps(item.get("payload_original", {}), ensure_ascii=False),
        )
        for item in indicators
    ]
    cur.executemany(
        """
        insert into public.mercado_indicadores(
          source_key,
          documento_id,
          indicador_key,
          indicador_nome,
          periodo_inicio,
          periodo_fim,
          periodo_label,
          geografia,
          unidade,
          valor,
          valor_texto,
          dimensoes,
          payload_original,
          coletado_em
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
        """,
        rows,
    )
    return len(rows)


def extract_aco_brasil_indicators(content: bytes) -> list[dict[str, Any]]:
    frame = pd.ExcelFile(BytesIO(content)).parse(0, header=None)
    rows = {
        7: ("aco_brasil_producao_aco_bruto", "Aco bruto", "mil t"),
        8: ("aco_brasil_producao_laminados", "Laminados", "mil t"),
        9: ("aco_brasil_producao_planos", "Planos", "mil t"),
        10: ("aco_brasil_producao_longos", "Longos", "mil t"),
        15: ("aco_brasil_vendas_internas_total", "Vendas internas", "mil t"),
        22: ("aco_brasil_vendas_externas_total", "Vendas externas", "mil t"),
        37: ("aco_brasil_exportacoes_total_toneladas", "Exportacoes totais", "mil t"),
        38: ("aco_brasil_exportacoes_total_usd", "Exportacoes totais", "US$ milhoes"),
        44: ("aco_brasil_importacoes_total_toneladas", "Importacoes totais", "mil t"),
        45: ("aco_brasil_importacoes_total_usd", "Importacoes totais", "US$ milhoes"),
        46: ("aco_brasil_consumo_aparente_total", "Consumo aparente", "mil t"),
    }
    indicators: list[dict[str, Any]] = []
    current_year: int | None = None
    for col in range(1, frame.shape[1]):
        parsed_year = year_value(frame.iat[3, col])
        if parsed_year:
            current_year = parsed_year
        period_start = parse_period_start(None, current_year, frame.iat[4, col])
        if not period_start:
            continue
        for row_idx, (key, name, unit) in rows.items():
            value = numeric_value(frame.iat[row_idx, col])
            if value is None:
                continue
            raw_label = clean_text(str(frame.iat[row_idx, 0]))
            indicators.append(
                {
                    "indicador_key": key,
                    "indicador_nome": name,
                    "periodo_inicio": period_start,
                    "periodo_label": period_start[:7],
                    "unidade": unit,
                    "valor": value,
                    "dimensoes": {"linha_original": raw_label},
                    "payload_original": {"sheet": "Perfomance Mensal-Monthly", "row": row_idx + 1, "column": col + 1},
                }
            )
    return indicators


def extract_cni_industrial_indicators(content: bytes) -> list[dict[str, Any]]:
    excel = pd.ExcelFile(BytesIO(content))
    indicators: list[dict[str, Any]] = []
    wanted_sheets = {
        "PRODU": ("cni_industria_producao", "Producao industrial"),
        "EMPREGADOS": ("cni_industria_empregados", "Numero de empregados"),
        "UCI (%)": ("cni_industria_uci_percentual", "Utilizacao da capacidade instalada"),
        "ESTOQUES (evolu": ("cni_industria_estoques_evolucao", "Evolucao dos estoques"),
        "ESTOQUES (efetivo": ("cni_industria_estoques_efetivo_planejado", "Estoque efetivo versus planejado"),
        "EXPECTATIVAS - DEMANDA": ("cni_industria_expectativa_demanda", "Expectativa de demanda"),
        "EXPECTATIVA - COMPRAS": ("cni_industria_expectativa_compras", "Expectativa de compras"),
        "EXPECTATIVA - EMPREGADOS": ("cni_industria_expectativa_empregados", "Expectativa de empregados"),
        "EXPECTATIVA - INVESTIMENTO": ("cni_industria_expectativa_investimento", "Expectativa de investimento"),
    }
    for sheet in excel.sheet_names:
        mapped = None
        for prefix, definition in wanted_sheets.items():
            if sheet.startswith(prefix):
                mapped = definition
                break
        if not mapped:
            continue
        key, name = mapped
        frame = excel.parse(sheet, header=None)
        if frame.shape[0] < 9:
            continue
        total_row = 8
        for col in range(1, frame.shape[1]):
            period_start = parse_period_start(frame.iat[7, col])
            if not period_start:
                continue
            value = numeric_value(frame.iat[total_row, col])
            if value is None:
                continue
            indicators.append(
                {
                    "indicador_key": key,
                    "indicador_nome": name,
                    "periodo_inicio": period_start,
                    "periodo_label": period_start[:7],
                    "unidade": "indice" if "uci_percentual" not in key else "%",
                    "valor": value,
                    "dimensoes": {"recorte": "industria_transformacao_e_extrativa"},
                    "payload_original": {"sheet": sheet, "row": total_row + 1, "column": col + 1},
                }
            )
    return indicators


def extract_cni_construcao_indicators(content: bytes) -> list[dict[str, Any]]:
    frame = pd.ExcelFile(BytesIO(content)).parse("indicadores", header=None)
    indicators: list[dict[str, Any]] = []
    indicator_rows: list[tuple[int, str]] = []
    for row_idx in range(frame.shape[0]):
        label = clean_text(str(frame.iat[row_idx, 1] if frame.shape[1] > 1 else ""))
        if re.match(r"^\d+\.\s+", label):
            indicator_rows.append((row_idx, label))
    for row_idx, title in indicator_rows:
        header_year_row = row_idx + 1
        header_month_row = row_idx + 2
        total_row = row_idx + 3
        if total_row >= frame.shape[0]:
            continue
        current_year: int | None = None
        key = "cni_construcao_" + normalize_key(title)
        name = re.sub(r"^\d+\.\s*", "", title)
        for col in range(2, frame.shape[1]):
            parsed_year = year_value(frame.iat[header_year_row, col])
            if parsed_year:
                current_year = parsed_year
            period_start = parse_period_start(None, current_year, frame.iat[header_month_row, col])
            if not period_start:
                continue
            value = numeric_value(frame.iat[total_row, col])
            if value is None:
                continue
            indicators.append(
                {
                    "indicador_key": key,
                    "indicador_nome": name,
                    "periodo_inicio": period_start,
                    "periodo_label": period_start[:7],
                    "unidade": "indice",
                    "valor": value,
                    "dimensoes": {"recorte": "total"},
                    "payload_original": {"sheet": "indicadores", "row": total_row + 1, "column": col + 1},
                }
            )
    return indicators


def extract_document_indicators(client: httpx.Client, document: dict[str, Any]) -> list[dict[str, Any]]:
    response = client.get(document["url"])
    response.raise_for_status()
    source_key = document["source_key"]
    if source_key == "aco_brasil_estatistica_mensal":
        return extract_aco_brasil_indicators(response.content)
    if source_key == "cni_sondagem_industrial":
        return extract_cni_industrial_indicators(response.content)
    if source_key == "cni_sondagem_construcao":
        return extract_cni_construcao_indicators(response.content)
    return []


def extract_market_indicators(source_keys: list[str], dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    timeout = int(env.get("EXTERNAL_DATA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
    headers = {"user-agent": env.get("EXTERNAL_DATA_USER_AGENT") or DEFAULT_USER_AGENT}
    result: dict[str, Any] = {"documents": []}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        with connect_database(env) as conn:
            with conn.cursor() as cur:
                documents = latest_planilha_documents(cur, source_keys)
                for document in documents:
                    try:
                        indicators = extract_document_indicators(client, document)
                        if not dry_run:
                            delete_document_indicators(cur, document["id"])
                            inserted = insert_indicators(cur, document, indicators)
                        else:
                            inserted = 0
                        result["documents"].append(
                            {
                                "source_key": document["source_key"],
                                "url": document["url"],
                                "indicators_found": len(indicators),
                                "indicators_inserted": inserted,
                                "sample": indicators[-5:],
                            }
                        )
                    except Exception as exc:
                        result["documents"].append(
                            {
                                "source_key": document["source_key"],
                                "url": document["url"],
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                if not dry_run:
                    conn.commit()
    return result


def collect_sources(source_keys: list[str], dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    timeout = int(env.get("EXTERNAL_DATA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
    headers = {"user-agent": env.get("EXTERNAL_DATA_USER_AGENT") or DEFAULT_USER_AGENT}
    selected = [PAGE_SOURCES[key] for key in source_keys]
    result: dict[str, Any] = {"sources": []}

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        if dry_run:
            for source in selected:
                page_url = env.get(source.env_url) or source.default_url
                documents = collect_page_source(client, source, page_url)
                result["sources"].append(
                    {
                        "source_key": source.key,
                        "page_url": page_url,
                        "documents_found": len(documents),
                        "documents": documents[:20],
                    }
                )
            return result

        with connect_database(env) as conn:
            with conn.cursor() as cur:
                for source in selected:
                    page_url = env.get(source.env_url) or source.default_url
                    run_id = start_run(cur, source.key, {"page_url": page_url, "env_url": source.env_url})
                    try:
                        documents = collect_page_source(client, source, page_url)
                        upserted = upsert_documents(cur, source.key, run_id, documents)
                        finish_run(cur, run_id, status="sucesso", found=len(documents), upserted=upserted)
                        result["sources"].append(
                            {
                                "source_key": source.key,
                                "status": "sucesso",
                                "page_url": page_url,
                                "documents_found": len(documents),
                                "documents_upserted": upserted,
                            }
                        )
                    except Exception as exc:
                        finish_run(cur, run_id, status="erro", error=f"{type(exc).__name__}: {exc}")
                        result["sources"].append(
                            {
                                "source_key": source.key,
                                "status": "erro",
                                "page_url": page_url,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                conn.commit()
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta fontes publicas de mercado para ABR Intelligence.")
    parser.add_argument(
        "--source",
        action="append",
        choices=[*PAGE_SOURCES.keys(), "all"],
        default=None,
        help="Fonte a coletar. Use varias vezes ou all.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Busca paginas e imprime documentos sem gravar no banco.")
    parser.add_argument("--skip-extract", action="store_true", help="Coleta documentos, mas nao extrai indicadores.")
    parser.add_argument("--extract-only", action="store_true", help="Nao coleta paginas; extrai indicadores das planilhas ja registradas.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested_sources = args.source or ["all"]
    source_keys = list(PAGE_SOURCES.keys()) if "all" in requested_sources else requested_sources
    result: dict[str, Any] = {}
    if not args.extract_only:
        result["collection"] = collect_sources(source_keys, dry_run=args.dry_run)
    if args.extract_only or not args.skip_extract:
        result["extraction"] = extract_market_indicators(source_keys, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
