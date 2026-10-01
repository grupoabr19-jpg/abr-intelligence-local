from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


PNCP_TERMS = {
    "estrutura metalica": 3,
    "cobertura metalica": 3,
    "telha metalica": 3,
    "perfil metalico": 3,
    "tubo de aco": 3,
    "metalon": 3,
    "chapa de aco": 3,
    "galpao": 2,
    "serralheria": 2,
    "ferragem": 2,
    "gradil": 2,
    "alambrado": 2,
    "estrutura de aco": 2,
    "aco": 1,
    "construcao": 1,
    "reforma": 1,
}

DEFAULT_PNCP_MODALITY_CODES = (
    "1",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
)


def normalize_text(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text)


def relevance_score(text: str) -> tuple[int, list[str]]:
    normalized = normalize_text(text)
    terms = [term for term in PNCP_TERMS if term in normalized]
    return sum(PNCP_TERMS[term] for term in terms), terms


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


def finish_run(cur: Any, run_id: str, *, status: str, found: int = 0, inserted: int = 0, error: str | None = None) -> None:
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
        (status, found, inserted, error, run_id),
    )


def active_count(cur: Any, table: str) -> int:
    cur.execute(f"select count(*) from public.{table} where ativo = true")
    return int(cur.fetchone()[0] or 0)


def collect_caged(dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            total_cnae = active_count(cur, "dim_cnae_abr")
            if total_cnae == 0:
                if not dry_run:
                    run_id = start_run(cur, "caged_microdados", {"reason": "dim_cnae_abr vazia"})
                    finish_run(
                        cur,
                        run_id,
                        status="parcial",
                        error="Nenhum CNAE ativo aprovado em dim_cnae_abr. CAGED nao foi baixado para evitar microdados desnecessarios.",
                    )
                    conn.commit()
                return {
                    "source_key": "caged_microdados",
                    "status": "sem_cnae_aprovado",
                    "message": "Cadastre CNAEs ativos em dim_cnae_abr antes de processar CAGED.",
                }
    return {"source_key": "caged_microdados", "status": "configurado", "message": "Processamento CAGED aguardando seletor de arquivo mensal."}


def pncp_base_url(env: dict[str, str]) -> str:
    configured = (env.get("PNCP_API_BASE_URL") or "https://pncp.gov.br/api/consulta/v1").strip().rstrip("/")
    if "/swagger-ui" in configured or "/api-docs" in configured:
        return "https://pncp.gov.br/api/consulta/v1"
    return configured


def pncp_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("data", "items", "content", "contratacoes"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return payload if isinstance(payload, list) else []


def collect_pncp(date_from: date, date_to: date, dry_run: bool = False) -> dict[str, Any]:
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute("select codigo from public.pncp_modality_codes where ativo = true")
            modalities = [str(row[0]) for row in cur.fetchall()]
    modality_filter = "configured" if modalities else "default_safe_set"
    modality_codes = modalities or list(DEFAULT_PNCP_MODALITY_CODES)

    rows_by_id: dict[str, dict[str, Any]] = {}
    skipped_modalities: list[dict[str, Any]] = []
    with httpx.Client(timeout=60, follow_redirects=True, headers={"user-agent": "ABR-Intelligence/1.0"}) as client:
        for modality_code in modality_codes:
            params = {
                "dataInicial": date_from.strftime("%Y%m%d"),
                "dataFinal": date_to.strftime("%Y%m%d"),
                "codigoModalidadeContratacao": modality_code,
                "pagina": 1,
                "tamanhoPagina": 50,
            }
            response = None
            for attempt in range(3):
                response = client.get(f"{pncp_base_url(env)}/contratacoes/publicacao", params=params)
                if response.status_code != 429:
                    break
                time.sleep(2 + attempt * 3)
            if response is None:
                continue
            if response.status_code == 204:
                time.sleep(0.4)
                continue
            if response.status_code == 429:
                skipped_modalities.append({"codigo": modality_code, "status_code": response.status_code})
                time.sleep(0.8)
                continue
            response.raise_for_status()
            for row in pncp_rows(response.json()):
                pncp_id = str(row.get("numeroControlePNCP") or row.get("id") or row.get("sequencialCompra") or "")
                if pncp_id:
                    rows_by_id[pncp_id] = row
            time.sleep(0.4)
    rows = list(rows_by_id.values())

    opportunities = []
    for row in rows:
        text = " ".join(str(row.get(key) or "") for key in ("objetoCompra", "objeto", "informacaoComplementar"))
        score, terms = relevance_score(text)
        if score <= 0:
            continue
        pncp_id = str(row.get("numeroControlePNCP") or row.get("id") or row.get("sequencialCompra"))
        opportunities.append(
            {
                "pncp_id": pncp_id,
                "data_publicacao": row.get("dataPublicacaoPncp") or row.get("dataPublicacao"),
                "modalidade_codigo": str(row.get("modalidadeId") or row.get("modalidadeCodigo") or ""),
                "orgao": row.get("orgaoEntidade", {}).get("razaoSocial") if isinstance(row.get("orgaoEntidade"), dict) else row.get("orgao"),
                "municipio": row.get("unidadeOrgao", {}).get("municipioNome") if isinstance(row.get("unidadeOrgao"), dict) else row.get("municipio"),
                "uf": row.get("unidadeOrgao", {}).get("ufSigla") if isinstance(row.get("unidadeOrgao"), dict) else row.get("uf"),
                "objeto": text,
                "valor_estimado": row.get("valorTotalEstimado") or row.get("valorEstimado"),
                "relevance_score": score,
                "termos_encontrados": terms,
                "payload_original": row,
            }
        )

    if dry_run:
        return {
            "source_key": "pncp_consulta",
            "status": "dry_run",
            "base_url": pncp_base_url(env),
            "modality_filter": modality_filter,
            "modalities": modality_codes,
            "skipped_modalities": skipped_modalities,
            "rows_found": len(rows),
            "opportunities_found": len(opportunities),
        }

    with connect_database(env) as conn:
        with conn.cursor() as cur:
            run_id = start_run(
                cur,
                "pncp_consulta",
                {
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                    "modalities": modality_codes,
                    "skipped_modalities": skipped_modalities,
                    "modality_filter": modality_filter,
                    "base_url": pncp_base_url(env),
                },
            )
            try:
                for item in opportunities:
                    cur.execute(
                        """
                        insert into public.raw_pncp(
                          pncp_id, data_publicacao, modalidade_codigo, orgao, municipio, uf, objeto,
                          valor_estimado, payload, coletado_em
                        )
                        values (%s, %s::date, %s, %s, %s, %s, %s, %s, %s::jsonb, now())
                        on conflict (pncp_id)
                        do update set
                          data_publicacao = excluded.data_publicacao,
                          modalidade_codigo = excluded.modalidade_codigo,
                          orgao = excluded.orgao,
                          municipio = excluded.municipio,
                          uf = excluded.uf,
                          objeto = excluded.objeto,
                          valor_estimado = excluded.valor_estimado,
                          payload = excluded.payload,
                          coletado_em = now()
                        """,
                        (
                            item["pncp_id"],
                            item["data_publicacao"],
                            item["modalidade_codigo"],
                            item["orgao"],
                            item["municipio"],
                            item["uf"],
                            item["objeto"],
                            item["valor_estimado"],
                            json.dumps(item["payload_original"], ensure_ascii=False),
                        ),
                    )
                    cur.execute(
                        """
                        insert into public.fact_pncp_opportunities(
                          pncp_id, data_publicacao, modalidade_codigo, orgao, municipio, uf, objeto,
                          valor_estimado, relevance_score, termos_encontrados, payload_original, coletado_em
                        )
                        values (%s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
                        on conflict (pncp_id)
                        do update set
                          data_publicacao = excluded.data_publicacao,
                          modalidade_codigo = excluded.modalidade_codigo,
                          orgao = excluded.orgao,
                          municipio = excluded.municipio,
                          uf = excluded.uf,
                          objeto = excluded.objeto,
                          valor_estimado = excluded.valor_estimado,
                          relevance_score = excluded.relevance_score,
                          termos_encontrados = excluded.termos_encontrados,
                          payload_original = excluded.payload_original,
                          coletado_em = now()
                        """,
                        (
                            item["pncp_id"],
                            item["data_publicacao"],
                            item["modalidade_codigo"],
                            item["orgao"],
                            item["municipio"],
                            item["uf"],
                            item["objeto"],
                            item["valor_estimado"],
                            item["relevance_score"],
                            json.dumps(item["termos_encontrados"], ensure_ascii=False),
                            json.dumps(item["payload_original"], ensure_ascii=False),
                        ),
                    )
                finish_run(cur, run_id, status="sucesso", found=len(rows), inserted=len(opportunities))
                conn.commit()
            except Exception as exc:
                finish_run(cur, run_id, status="erro", found=len(rows), inserted=0, error=f"{type(exc).__name__}: {exc}")
                conn.commit()
                raise
    return {
        "source_key": "pncp_consulta",
        "status": "sucesso",
        "base_url": pncp_base_url(env),
        "modality_filter": modality_filter,
        "modalities": modality_codes,
        "skipped_modalities": skipped_modalities,
        "rows_found": len(rows),
        "opportunities_inserted": len(opportunities),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta fontes governamentais de mercado: CAGED e PNCP.")
    parser.add_argument("--source", action="append", choices=["caged", "pncp", "all"], default=None)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested = args.source or ["all"]
    today = date.today()
    date_from = date.fromisoformat(args.date_from) if args.date_from else today - timedelta(days=7)
    date_to = date.fromisoformat(args.date_to) if args.date_to else today
    result: dict[str, Any] = {"sources": []}
    if "all" in requested or "caged" in requested:
        result["sources"].append(collect_caged(dry_run=args.dry_run))
    if "all" in requested or "pncp" in requested:
        result["sources"].append(collect_pncp(date_from, date_to, dry_run=args.dry_run))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
