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


def int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def number_or_none(value: Any) -> Any:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
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


def fetch_users(client: httpx.Client, limit: int, max_pages: int) -> tuple[list[dict[str, Any]], dict[int, str]]:
    users = get_pages(client, "/api/v4/users", "users", params={"with": "role,group"}, limit=limit, max_pages=max_pages)
    index = {int(user["id"]): str(user.get("name") or user.get("email") or user["id"]) for user in users if user.get("id")}
    return users, index


def fetch_pipelines(client: httpx.Client) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, str], dict[int, str]]:
    response = client.get("/api/v4/leads/pipelines")
    response.raise_for_status()
    pipelines = page_items(response.json(), "pipelines")
    pipeline_names: dict[int, str] = {}
    status_names: dict[int, str] = {}
    statuses: list[dict[str, Any]] = []
    for pipeline in pipelines:
        pipeline_id = pipeline.get("id")
        if pipeline_id is None:
            continue
        pipeline_names[int(pipeline_id)] = str(pipeline.get("name") or pipeline_id)
        for status in embedded_items(pipeline, "statuses"):
            status_id = status.get("id")
            if status_id is not None:
                status_names[int(status_id)] = str(status.get("name") or status_id)
                statuses.append({**status, "_pipeline_id": int(pipeline_id)})
    return pipelines, statuses, pipeline_names, status_names


def fetch_open_tasks_by_lead(client: httpx.Client, limit: int, max_pages: int) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
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
    return tasks, index


def fetch_events(
    client: httpx.Client,
    date_from: str | None,
    date_to: str | None,
    limit: int,
    max_pages: int,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        events = get_pages(
            client,
            "/api/v4/events",
            "events",
            params={
                "filter[entity]": "lead",
                "filter[created_at][from]": unix_date(date_from),
                "filter[created_at][to]": unix_date(date_to, end_of_day=True),
            },
            limit=limit,
            max_pages=max_pages,
        )
        return events, None
    except httpx.HTTPStatusError as exc:
        return [], f"{exc.response.status_code}: {exc.response.text[:240]}"
    except httpx.HTTPError as exc:
        return [], str(exc)[:240]


def custom_field_value(lead: dict[str, Any], field_reference: str | None) -> Any:
    if not field_reference:
        return None
    reference = field_reference.strip()
    expected_name = reference.casefold()
    expected_id = int(reference) if reference.isdigit() else None
    for field in lead.get("custom_fields_values") or []:
        field_id = field.get("field_id")
        field_name = str(field.get("field_name") or "").strip().casefold()
        if expected_id is not None:
            try:
                if int(field_id or 0) != expected_id:
                    continue
            except (TypeError, ValueError):
                continue
        elif field_name != expected_name:
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
        "Primeira acao humana": first_response,
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
        raw_users, users = fetch_users(client, limit, max_pages)
        progress(f"usuarios encontrados: {len(users)}")
        progress("buscando funis e etapas")
        raw_pipelines, raw_statuses, pipeline_names, status_names = fetch_pipelines(client)
        progress(f"funis encontrados: {len(pipeline_names)}")
        progress("buscando tarefas abertas")
        raw_tasks, tasks_by_lead = fetch_open_tasks_by_lead(client, limit, max_pages)
        progress(f"tarefas abertas vinculadas a leads: {len(tasks_by_lead)}")
        raw_events: list[dict[str, Any]] = []
        events_error = None
        collect_events = (env.get("KOMMO_COLLECT_EVENTS") or "").strip().lower() in {"1", "true", "sim", "yes"}
        if collect_events:
            progress("buscando eventos de leads")
            raw_events, events_error = fetch_events(client, date_from, date_to, limit, max_pages)
            if events_error:
                progress(f"eventos indisponiveis: {events_error}")
            else:
                progress(f"eventos encontrados: {len(raw_events)}")
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
        "raw": {
            "users": raw_users,
            "pipelines": raw_pipelines,
            "statuses": raw_statuses,
            "leads": leads,
            "tasks": raw_tasks,
            "events": raw_events,
        },
        "events_error": events_error,
    }


def insert_current_versions(
    cur: Any,
    *,
    table: str,
    id_column: str,
    records: list[dict[str, Any]],
    insert_sql: str,
    insert_rows: list[tuple[Any, ...]],
) -> dict[str, int]:
    if not records:
        return {"raw_inserted": 0, "raw_skipped": 0}

    source_ids = [record[id_column] for record in records]
    hashes = [record["raw_hash"] for record in records]
    cur.execute(
        f"""
        select {id_column}, raw_hash
        from public.{table}
        where ativo = true
          and {id_column} = any(%s)
        """,
        (source_ids,),
    )
    active_hashes = {(row[0], row[1]) for row in cur.fetchall()}
    new_indexes = [idx for idx, record in enumerate(records) if (record[id_column], record["raw_hash"]) not in active_hashes]
    skipped = len(records) - len(new_indexes)
    if not new_indexes:
        return {"raw_inserted": 0, "raw_skipped": skipped}

    changed_source_ids = [records[idx][id_column] for idx in new_indexes]
    cur.execute(
        f"""
        update public.{table}
        set ativo = false,
            updated_at = now()
        where ativo = true
          and {id_column} = any(%s)
        """,
        (changed_source_ids,),
    )
    cur.executemany(insert_sql, [insert_rows[idx] for idx in new_indexes])
    return {"raw_inserted": len(new_indexes), "raw_skipped": skipped}


def insert_raw_data(cur: Any, raw: dict[str, list[dict[str, Any]]], sync_id: str) -> dict[str, int]:
    raw_inserted = 0
    raw_skipped = 0

    user_records = [
        {
            "kommo_user_id": int(user["id"]),
            "raw_hash": row_hash(user),
        }
        for user in raw.get("users", [])
        if user.get("id") is not None
    ]
    user_rows = [
        (
            int(user["id"]),
            user.get("name"),
            user.get("email"),
            json.dumps(user, ensure_ascii=False),
            row_hash(user),
            sync_id,
        )
        for user in raw.get("users", [])
        if user.get("id") is not None
    ]
    result = insert_current_versions(
        cur,
        table="raw_kommo_users",
        id_column="kommo_user_id",
        records=user_records,
        insert_sql="""
            insert into public.raw_kommo_users(
              kommo_user_id, name, email, raw_payload, raw_hash, sync_id, ativo, fetched_at
            )
            values (%s, %s, %s, %s::jsonb, %s, %s, true, now())
            on conflict (kommo_user_id, raw_hash) do update
            set ativo = true, sync_id = excluded.sync_id, fetched_at = now(), updated_at = now()
        """,
        insert_rows=user_rows,
    )
    raw_inserted += result["raw_inserted"]
    raw_skipped += result["raw_skipped"]

    pipeline_records = [
        {"kommo_pipeline_id": int(pipeline["id"]), "raw_hash": row_hash(pipeline)}
        for pipeline in raw.get("pipelines", [])
        if pipeline.get("id") is not None
    ]
    pipeline_rows = [
        (
            int(pipeline["id"]),
            pipeline.get("name"),
            json.dumps(pipeline, ensure_ascii=False),
            row_hash(pipeline),
            sync_id,
        )
        for pipeline in raw.get("pipelines", [])
        if pipeline.get("id") is not None
    ]
    result = insert_current_versions(
        cur,
        table="raw_kommo_pipelines",
        id_column="kommo_pipeline_id",
        records=pipeline_records,
        insert_sql="""
            insert into public.raw_kommo_pipelines(
              kommo_pipeline_id, name, raw_payload, raw_hash, sync_id, ativo, fetched_at
            )
            values (%s, %s, %s::jsonb, %s, %s, true, now())
            on conflict (kommo_pipeline_id, raw_hash) do update
            set ativo = true, sync_id = excluded.sync_id, fetched_at = now(), updated_at = now()
        """,
        insert_rows=pipeline_rows,
    )
    raw_inserted += result["raw_inserted"]
    raw_skipped += result["raw_skipped"]

    status_records = [
        {"kommo_status_id": int(status["id"]), "raw_hash": row_hash(status)}
        for status in raw.get("statuses", [])
        if status.get("id") is not None
    ]
    status_rows = [
        (
            int(status["id"]),
            int_or_none(status.get("_pipeline_id")),
            status.get("name"),
            json.dumps(status, ensure_ascii=False),
            row_hash(status),
            sync_id,
        )
        for status in raw.get("statuses", [])
        if status.get("id") is not None
    ]
    result = insert_current_versions(
        cur,
        table="raw_kommo_statuses",
        id_column="kommo_status_id",
        records=status_records,
        insert_sql="""
            insert into public.raw_kommo_statuses(
              kommo_status_id, kommo_pipeline_id, name, raw_payload, raw_hash, sync_id, ativo, fetched_at
            )
            values (%s, %s, %s, %s::jsonb, %s, %s, true, now())
            on conflict (kommo_status_id, raw_hash) do update
            set ativo = true, sync_id = excluded.sync_id, fetched_at = now(), updated_at = now()
        """,
        insert_rows=status_rows,
    )
    raw_inserted += result["raw_inserted"]
    raw_skipped += result["raw_skipped"]

    lead_records = [
        {"kommo_lead_id": int(lead["id"]), "raw_hash": row_hash(lead)}
        for lead in raw.get("leads", [])
        if lead.get("id") is not None
    ]
    lead_rows = [
        (
            int(lead["id"]),
            int_or_none(lead.get("pipeline_id")),
            int_or_none(lead.get("status_id")),
            int_or_none(lead.get("responsible_user_id")),
            lead.get("name"),
            number_or_none(lead.get("price")),
            iso_from_unix(lead.get("created_at")),
            iso_from_unix(lead.get("updated_at")),
            iso_from_unix(lead.get("closed_at")),
            json.dumps(lead, ensure_ascii=False),
            row_hash(lead),
            sync_id,
        )
        for lead in raw.get("leads", [])
        if lead.get("id") is not None
    ]
    result = insert_current_versions(
        cur,
        table="raw_kommo_leads",
        id_column="kommo_lead_id",
        records=lead_records,
        insert_sql="""
            insert into public.raw_kommo_leads(
              kommo_lead_id, kommo_pipeline_id, kommo_status_id, responsible_user_id,
              name, price, created_at_kommo, updated_at_kommo, closed_at_kommo,
              raw_payload, raw_hash, sync_id, ativo, fetched_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, true, now())
            on conflict (kommo_lead_id, raw_hash) do update
            set ativo = true, sync_id = excluded.sync_id, fetched_at = now(), updated_at = now()
        """,
        insert_rows=lead_rows,
    )
    raw_inserted += result["raw_inserted"]
    raw_skipped += result["raw_skipped"]

    task_records = [
        {"kommo_task_id": int(task["id"]), "raw_hash": row_hash(task)}
        for task in raw.get("tasks", [])
        if task.get("id") is not None
    ]
    task_rows = [
        (
            int(task["id"]),
            task.get("entity_type"),
            int_or_none(task.get("entity_id")),
            int_or_none(task.get("responsible_user_id")),
            bool(task.get("is_completed")) if task.get("is_completed") is not None else None,
            iso_from_unix(task.get("complete_till")),
            json.dumps(task, ensure_ascii=False),
            row_hash(task),
            sync_id,
        )
        for task in raw.get("tasks", [])
        if task.get("id") is not None
    ]
    result = insert_current_versions(
        cur,
        table="raw_kommo_tasks",
        id_column="kommo_task_id",
        records=task_records,
        insert_sql="""
            insert into public.raw_kommo_tasks(
              kommo_task_id, entity_type, entity_id, responsible_user_id, is_completed,
              complete_till_kommo, raw_payload, raw_hash, sync_id, ativo, fetched_at
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, true, now())
            on conflict (kommo_task_id, raw_hash) do update
            set ativo = true, sync_id = excluded.sync_id, fetched_at = now(), updated_at = now()
        """,
        insert_rows=task_rows,
    )
    raw_inserted += result["raw_inserted"]
    raw_skipped += result["raw_skipped"]

    event_records = [
        {"kommo_event_id": str(event["id"]), "raw_hash": row_hash(event)}
        for event in raw.get("events", [])
        if event.get("id") is not None
    ]
    event_rows = [
        (
            str(event["id"]),
            event.get("entity_type"),
            int_or_none(event.get("entity_id")),
            event.get("type"),
            int_or_none(event.get("created_by")),
            iso_from_unix(event.get("created_at")),
            json.dumps(event, ensure_ascii=False),
            row_hash(event),
            sync_id,
        )
        for event in raw.get("events", [])
        if event.get("id") is not None
    ]
    result = insert_current_versions(
        cur,
        table="raw_kommo_events",
        id_column="kommo_event_id",
        records=event_records,
        insert_sql="""
            insert into public.raw_kommo_events(
              kommo_event_id, entity_type, entity_id, event_type, created_by,
              created_at_kommo, raw_payload, raw_hash, sync_id, ativo, fetched_at
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, true, now())
            on conflict (kommo_event_id, raw_hash) do update
            set ativo = true, sync_id = excluded.sync_id, fetched_at = now(), updated_at = now()
        """,
        insert_rows=event_rows,
    )
    raw_inserted += result["raw_inserted"]
    raw_skipped += result["raw_skipped"]

    return {"raw_inserted": raw_inserted, "raw_skipped": raw_skipped}


def insert_rows(collected: dict[str, Any], date_from: str | None = None, date_to: str | None = None) -> dict[str, int]:
    env = load_env()
    sync_id = f"kommo_api_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    rows = collected["rows"]
    records: list[tuple[str, str, str, str, str, str, str]] = []
    for row in rows:
        lead_id = row.get("ID do lead")
        source_id = f"kommo_lead:{lead_id}"
        payload = json.dumps(row, ensure_ascii=False)
        records.append((SOURCE_SYSTEM, source_id, ENTITY, payload, payload, sync_id, row_hash(row)))

    progress(f"gravando raw e staging: {len(rows)} leads normalizados")

    source_ids = [record[1] for record in records]
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            raw_result = insert_raw_data(cur, collected.get("raw", {}), sync_id)
            cur.execute(
                """
                insert into public.atendimento_ingestion_runs(
                  sync_id, status, date_from, date_to, page_limit, max_pages,
                  users_lidos, pipelines_lidos, statuses_lidos, leads_lidos, tasks_lidas, events_lidos,
                  raw_inseridos, raw_ignorados, events_status, events_erro, metadata
                )
                values (%s, 'processando', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict (sync_id) do nothing
                """,
                (
                    sync_id,
                    date_from,
                    date_to,
                    int(env.get("KOMMO_PAGE_LIMIT") or DEFAULT_LIMIT),
                    int(env.get("KOMMO_MAX_PAGES") or DEFAULT_MAX_PAGES),
                    len(collected.get("raw", {}).get("users", [])),
                    len(collected.get("raw", {}).get("pipelines", [])),
                    len(collected.get("raw", {}).get("statuses", [])),
                    len(collected.get("raw", {}).get("leads", [])),
                    len(collected.get("raw", {}).get("tasks", [])),
                    len(collected.get("raw", {}).get("events", [])),
                    raw_result["raw_inserted"],
                    raw_result["raw_skipped"],
                    "erro" if collected.get("events_error") else "sucesso",
                    collected.get("events_error"),
                    json.dumps({"base_url": collected.get("base_url")}, ensure_ascii=False),
                ),
            )
            if not records:
                cur.execute(
                    """
                    update public.atendimento_ingestion_runs
                    set status = 'sucesso',
                        finished_at = now(),
                        raw_inseridos = %s,
                        raw_ignorados = %s
                    where sync_id = %s
                    """,
                    (raw_result["raw_inserted"], raw_result["raw_skipped"], sync_id),
                )
                conn.commit()
                return {"inserted": 0, "skipped": 0, **raw_result}
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
            inserted = len(new_records)
            cur.execute(
                """
                update public.atendimento_ingestion_runs
                set status = 'sucesso',
                    finished_at = now(),
                    staging_inseridos = %s,
                    staging_ignorados = %s
                where sync_id = %s
                """,
                (inserted, skipped, sync_id),
            )
            conn.commit()
    progress(
        "ingestao concluida: "
        f"raw_inserted={raw_result['raw_inserted']}, raw_skipped={raw_result['raw_skipped']}, "
        f"staging_inserted={inserted}, staging_skipped={skipped}"
    )
    return {"inserted": inserted, "skipped": skipped, **raw_result}


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
        "events_found": len(collected.get("raw", {}).get("events", [])),
        "events_error": collected.get("events_error"),
        "fields": list(collected["rows"][0].keys()) if collected["rows"] else [],
    }
    if not args.dry_run:
        result.update(insert_rows(collected, args.date_from, args.date_to))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
