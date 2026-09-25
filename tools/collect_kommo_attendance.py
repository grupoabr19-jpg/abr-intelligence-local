from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


DEFAULT_TIMEOUT = 60
DEFAULT_LIMIT = 250
DEFAULT_MAX_PAGES = 100
SOURCE_SYSTEM = "KOMMO_API"
ENTITY = "atendimento_kommo"


def progress(message: str) -> None:
    print(f"[kommo] {message}", file=sys.stderr, flush=True)


def clean_base_url(env: dict[str, str]) -> str:
    base_url = (env.get("KOMMO_API_BASE_URL") or "").strip().rstrip("/")
    subdomain = (env.get("KOMMO_SUBDOMAIN") or "").strip().strip("/")
    if not base_url and subdomain:
        base_url = f"https://{subdomain}.kommo.com"
    if not base_url:
        raise SystemExit("Configure KOMMO_API_BASE_URL ou KOMMO_SUBDOMAIN no .env.")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("KOMMO_API_BASE_URL invalida. Use formato https://<subdominio>.kommo.com.")
    return base_url


def access_token(env: dict[str, str], base_url: str, timeout: int) -> str:
    token = (env.get("KOMMO_ACCESS_TOKEN") or "").strip()
    if token:
        return token

    refresh_token = (env.get("KOMMO_REFRESH_TOKEN") or "").strip()
    client_id = (env.get("KOMMO_CLIENT_ID") or "").strip()
    client_secret = (env.get("KOMMO_CLIENT_SECRET") or "").strip()
    redirect_uri = (env.get("KOMMO_REDIRECT_URI") or "").strip()
    if not all((refresh_token, client_id, client_secret, redirect_uri)):
        raise SystemExit(
            "Configure KOMMO_ACCESS_TOKEN ou KOMMO_REFRESH_TOKEN + KOMMO_CLIENT_ID + KOMMO_CLIENT_SECRET + KOMMO_REDIRECT_URI."
        )

    response = httpx.post(
        f"{base_url}/oauth2/access_token",
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": redirect_uri,
        },
        timeout=timeout,
        headers={"accept": "application/json", "content-type": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise SystemExit("Kommo nao retornou access_token ao renovar credenciais.")
    return str(token)


def unix_date(value: str | None, end_of_day: bool = False) -> int | None:
    if not value:
        return None
    parsed = date.fromisoformat(value)
    dt = datetime(parsed.year, parsed.month, parsed.day, 23, 59, 59 if end_of_day else 0, tzinfo=timezone.utc)
    if not end_of_day:
        dt = datetime(parsed.year, parsed.month, parsed.day, 0, 0, 0, tzinfo=timezone.utc)
    return int(dt.timestamp())


def iso_from_unix(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def embedded_items(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get("_embedded", {}).get(key)
    return value if isinstance(value, list) else []


def page_items(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get("_embedded", {}).get(key)
    return value if isinstance(value, list) else []


def get_pages(
    client: httpx.Client,
    path: str,
    embedded_key: str,
    *,
    params: dict[str, Any] | None = None,
    limit: int = DEFAULT_LIMIT,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        request_params = {"page": page, "limit": limit}
        if params:
            request_params.update({key: value for key, value in params.items() if value not in (None, "")})
        response = client.get(path, params=request_params)
        if response.status_code == 204:
            break
        response.raise_for_status()
        payload = response.json()
        items = page_items(payload, embedded_key)
        if not items:
            break
        rows.extend(items)
        next_link = payload.get("_links", {}).get("next", {}).get("href")
        if not next_link or len(items) < limit:
            break
    return rows


def user_index(client: httpx.Client, limit: int, max_pages: int) -> dict[int, str]:
    users = get_pages(client, "/api/v4/users", "users", params={"with": "role,group"}, limit=limit, max_pages=max_pages)
    return {int(user["id"]): str(user.get("name") or user.get("email") or user["id"]) for user in users if user.get("id")}


def pipeline_indexes(client: httpx.Client) -> tuple[dict[int, str], dict[int, str]]:
    response = client.get("/api/v4/leads/pipelines")
    response.raise_for_status()
    pipelines = page_items(response.json(), "pipelines")
    pipeline_names: dict[int, str] = {}
    status_names: dict[int, str] = {}
    for pipeline in pipelines:
        pipeline_id = pipeline.get("id")
        if pipeline_id is None:
            continue
        pipeline_names[int(pipeline_id)] = str(pipeline.get("name") or pipeline_id)
        for status in embedded_items(pipeline, "statuses"):
            status_id = status.get("id")
            if status_id is not None:
                status_names[int(status_id)] = str(status.get("name") or status_id)
    return pipeline_names, status_names


def open_tasks_by_lead(client: httpx.Client, limit: int, max_pages: int) -> dict[int, dict[str, Any]]:
    tasks = get_pages(
        client,
        "/api/v4/tasks",
        "tasks",
        params={"filter[entity_type]": "leads", "filter[is_completed]": 0},
        limit=limit,
        max_pages=max_pages,
    )
    index: dict[int, dict[str, Any]] = {}
    for task in tasks:
        entity_id = task.get("entity_id")
        if entity_id is None:
            continue
        lead_id = int(entity_id)
        current = index.get(lead_id)
        if current is None or int(task.get("complete_till") or 0) < int(current.get("complete_till") or 0):
            index[lead_id] = task
    return index


def custom_field_value(lead: dict[str, Any], field_name: str | None) -> Any:
    if not field_name:
        return None
    expected = field_name.strip().casefold()
    for field in lead.get("custom_fields_values") or []:
        if str(field.get("field_name") or "").strip().casefold() != expected:
            continue
        values = field.get("values") or []
        if not values:
            return None
        first = values[0]
        if isinstance(first, dict):
            return first.get("value") or first.get("enum") or first.get("enum_code")
        return first
    return None


def lead_stage_name(lead: dict[str, Any], status_names: dict[int, str]) -> str:
    status_id = int(lead.get("status_id") or 0)
    if status_id == 142:
        return "Venda ganha"
    if status_id == 143:
        return "Venda perdida"
    return status_names.get(status_id, str(status_id or "Sem etapa"))


def normalize_lead(
    lead: dict[str, Any],
    env: dict[str, str],
    users: dict[int, str],
    pipeline_names: dict[int, str],
    status_names: dict[int, str],
    tasks_by_lead: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    lead_id = int(lead["id"])
    responsible_id = lead.get("responsible_user_id")
    pipeline_id = int(lead.get("pipeline_id") or 0)
    status_id = int(lead.get("status_id") or 0)
    source = lead.get("_embedded", {}).get("source") or {}
    task = tasks_by_lead.get(lead_id)
    first_contact = custom_field_value(lead, env.get("KOMMO_FIELD_FIRST_CONTACT"))
    first_response = custom_field_value(lead, env.get("KOMMO_FIELD_FIRST_RESPONSE"))
    wait_minutes = custom_field_value(lead, env.get("KOMMO_FIELD_WAIT_MINUTES"))

    return {
        "ID do lead": str(lead_id),
        "Nome do lead": lead.get("name"),
        "Criado em": iso_from_unix(lead.get("created_at")),
        "Atualizado em": iso_from_unix(lead.get("updated_at")),
        "Fechado em": iso_from_unix(lead.get("closed_at")),
        "Situacao": "Aberto" if not lead.get("closed_at") else "Fechado",
        "Funil": pipeline_names.get(pipeline_id, str(pipeline_id or "Sem funil")),
        "Etapa": lead_stage_name(lead, status_names),
        "Status ID": str(status_id),
        "Pipeline ID": str(pipeline_id) if pipeline_id else None,
        "Primeiro contato recebido": first_contact,
        "Primeira resposta humana": first_response,
        "Espera em minutos": wait_minutes,
        "Valor": lead.get("price"),
        "Proxima tarefa": iso_from_unix((task or {}).get("complete_till") or lead.get("closest_task_at")),
        "Ultima interacao": iso_from_unix(lead.get("updated_at")),
        "Origem": custom_field_value(lead, env.get("KOMMO_FIELD_ORIGIN")) or source.get("name"),
        "Regiao": custom_field_value(lead, env.get("KOMMO_FIELD_REGION")),
        "Segmento": custom_field_value(lead, env.get("KOMMO_FIELD_SEGMENT")),
        "Temperatura": custom_field_value(lead, env.get("KOMMO_FIELD_TEMPERATURE")),
        "Responsavel": users.get(int(responsible_id or 0), str(responsible_id or "")),
        "Responsavel ID": str(responsible_id) if responsible_id else None,
        "Quem respondeu primeiro": users.get(int(lead.get("updated_by") or 0), str(lead.get("updated_by") or "")),
        "Link Kommo": f"{clean_base_url(env)}/leads/detail/{lead_id}",
        "_kommo": lead,
    }


def row_hash(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def collect_rows(
    env: dict[str, str],
    date_from: str | None,
    date_to: str | None,
    *,
    page_limit: int | None = None,
    max_pages: int | None = None,
) -> dict[str, Any]:
    timeout = int(env.get("EXTERNAL_DATA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
    limit = min(page_limit or int(env.get("KOMMO_PAGE_LIMIT") or DEFAULT_LIMIT), DEFAULT_LIMIT)
    max_pages = max_pages or int(env.get("KOMMO_MAX_PAGES") or DEFAULT_MAX_PAGES)
    base_url = clean_base_url(env)
    token = access_token(env, base_url, timeout)
    headers = {"authorization": f"Bearer {token}", "accept": "application/json"}

    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout, follow_redirects=True) as client:
        progress("buscando usuarios")
        users = user_index(client, limit, max_pages)
        progress(f"usuarios encontrados: {len(users)}")
        progress("buscando funis e etapas")
        pipeline_names, status_names = pipeline_indexes(client)
        progress(f"funis encontrados: {len(pipeline_names)}")
        progress("buscando tarefas abertas")
        tasks_by_lead = open_tasks_by_lead(client, limit, max_pages)
        progress(f"tarefas abertas vinculadas a leads: {len(tasks_by_lead)}")
        lead_params: dict[str, Any] = {
            "with": "contacts,source,loss_reason",
            "order[created_at]": "asc",
            "filter[created_at][from]": unix_date(date_from),
            "filter[created_at][to]": unix_date(date_to, end_of_day=True),
        }
        progress("buscando leads")
        leads = get_pages(client, "/api/v4/leads", "leads", params=lead_params, limit=limit, max_pages=max_pages)
        progress(f"leads encontrados: {len(leads)}")
        rows = [normalize_lead(lead, env, users, pipeline_names, status_names, tasks_by_lead) for lead in leads]

    return {
        "base_url": base_url,
        "rows": rows,
        "leads_found": len(rows),
        "users_found": len(users),
        "pipelines_found": len(pipeline_names),
        "open_tasks_found": len(tasks_by_lead),
    }


def insert_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    env = load_env()
    sync_id = f"kommo_api_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    records: list[tuple[str, str, str, str, str, str, str]] = []
    for row in rows:
        lead_id = row.get("ID do lead")
        source_id = f"kommo_lead:{lead_id}"
        payload = json.dumps(row, ensure_ascii=False)
        records.append((SOURCE_SYSTEM, source_id, ENTITY, payload, payload, sync_id, row_hash(row)))

    progress(f"gravando staging: {len(rows)} linhas")
    if not records:
        return {"inserted": 0, "skipped": 0}

    source_ids = [record[1] for record in records]
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select source_id, hash_registro
                from public.staging_dados
                where source_system = %s
                  and entidade = %s
                  and ativo = true
                  and source_id = any(%s)
                """,
                (SOURCE_SYSTEM, ENTITY, source_ids),
            )
            active_hashes = {(str(source_id), str(hash_value)) for source_id, hash_value in cur.fetchall()}
            new_records = [record for record in records if (record[1], record[6]) not in active_hashes]
            skipped = len(records) - len(new_records)

            if new_records:
                changed_source_ids = [record[1] for record in new_records]
                cur.execute(
                    """
                    update public.staging_dados
                    set ativo = false,
                        updated_at = now()
                    where source_system = %s
                      and entidade = %s
                      and ativo = true
                      and source_id = any(%s)
                    """,
                    (SOURCE_SYSTEM, ENTITY, changed_source_ids),
                )
                cur.executemany(
                    """
                    insert into public.staging_dados(
                      source_system,
                      source_id,
                      entidade,
                      payload_original,
                      dados_transformados,
                      sync_id,
                      hash_registro,
                      status_validacao,
                      tabela_destino,
                      ativo
                    )
                    values (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, 'pendente', 'atendimento_kommo', true)
                    """,
                    new_records,
                )
            conn.commit()
    inserted = len(new_records)
    progress(f"staging concluido: inserted={inserted}, skipped={skipped}")
    return {"inserted": inserted, "skipped": skipped}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta dados de atendimento diretamente da API Kommo.")
    parser.add_argument("--dry-run", action="store_true", help="Consulta a API e mostra resumo sem gravar.")
    parser.add_argument("--date-from", help="Data inicial de criacao do lead em YYYY-MM-DD.")
    parser.add_argument("--date-to", help="Data final de criacao do lead em YYYY-MM-DD.")
    parser.add_argument("--page-limit", type=int, help="Quantidade de registros por pagina, ate 250.")
    parser.add_argument("--max-pages", type=int, help="Quantidade maxima de paginas por endpoint nesta execucao.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    collected = collect_rows(
        env,
        args.date_from,
        args.date_to,
        page_limit=args.page_limit,
        max_pages=args.max_pages,
    )
    result: dict[str, Any] = {
        "source_system": SOURCE_SYSTEM,
        "base_url": collected["base_url"],
        "rows_found": collected["leads_found"],
        "users_found": collected["users_found"],
        "pipelines_found": collected["pipelines_found"],
        "open_tasks_found": collected["open_tasks_found"],
        "fields": list(collected["rows"][0].keys()) if collected["rows"] else [],
    }
    if not args.dry_run:
        result.update(insert_rows(collected["rows"]))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
