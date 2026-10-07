from __future__ import annotations

import base64
import csv
import hashlib
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from tools.apply_migrations import connect_database, load_env


ROOT = Path(__file__).resolve().parents[1]
DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


@dataclass
class ArchiveConfig:
    provider: str
    local_dir: Path
    write_local_copy: bool
    drive_folder_id: str
    oauth_client_id: str
    oauth_client_secret: str
    oauth_refresh_token: str
    service_account_json: str
    service_account_json_base64: str
    service_account_json_path: str


def archive_config(env: dict[str, str] | None = None) -> ArchiveConfig:
    values = env or load_env()
    return ArchiveConfig(
        provider=values.get("ARCHIVE_STORAGE_PROVIDER", "local").strip().lower(),
        local_dir=Path(values.get("ARCHIVE_LOCAL_DIR", "archive")),
        write_local_copy=values.get("ARCHIVE_WRITE_LOCAL_COPY", "true").strip().lower() not in {"0", "false", "no"},
        drive_folder_id=values.get("ARCHIVE_GOOGLE_DRIVE_FOLDER_ID", "").strip(),
        oauth_client_id=values.get("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        oauth_client_secret=values.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip(),
        oauth_refresh_token=values.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip(),
        service_account_json=values.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip(),
        service_account_json_base64=values.get("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "").strip(),
        service_account_json_path=values.get("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "").strip(),
    )


def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return text.strip("._-").lower() or "sem_nome"


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def normalized_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            normalized[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)
        else:
            normalized[key] = value
    return normalized


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file_obj:
        for row in rows:
            file_obj.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=json_default))
            file_obj.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(normalized_row(row))


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    frame = pd.DataFrame([normalized_row(row) for row in rows])
    for column in frame.columns:
        frame[column] = frame[column].map(lambda value: None if pd.isna(value) else str(value))
    frame.to_parquet(path, index=False)


def service_account_info(config: ArchiveConfig) -> dict[str, Any] | None:
    if config.service_account_json:
        return json.loads(config.service_account_json)
    if config.service_account_json_base64:
        decoded = base64.b64decode(config.service_account_json_base64).decode("utf-8")
        return json.loads(decoded)
    if config.service_account_json_path:
        path = Path(config.service_account_json_path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def access_token_from_service_account(config: ArchiveConfig) -> str | None:
    info = service_account_info(config)
    if not info:
        return None
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(info, scopes=[DRIVE_SCOPE])
    credentials.refresh(Request())
    return credentials.token


def access_token_from_oauth(config: ArchiveConfig) -> str | None:
    if not (config.oauth_client_id and config.oauth_client_secret and config.oauth_refresh_token):
        return None
    with httpx.Client(timeout=60) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": config.oauth_client_id,
                "client_secret": config.oauth_client_secret,
                "refresh_token": config.oauth_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return str(response.json()["access_token"])


def drive_access_token(config: ArchiveConfig) -> str | None:
    try:
        token = access_token_from_oauth(config)
    except Exception:
        token = None
    return token or access_token_from_service_account(config)


def drive_headers(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def drive_query_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def ensure_drive_folder(token: str, parent_id: str, name: str) -> str:
    query = (
        f"name = '{drive_query_literal(name)}' "
        f"and mimeType = '{DRIVE_FOLDER_MIME}' "
        f"and '{drive_query_literal(parent_id)}' in parents and trashed = false"
    )
    with httpx.Client(timeout=60) as client:
        response = client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers=drive_headers(token),
            params={
                "q": query,
                "fields": "files(id,name)",
                "pageSize": "1",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        response.raise_for_status()
        files = response.json().get("files") or []
        if files:
            return str(files[0]["id"])
        response = client.post(
            "https://www.googleapis.com/drive/v3/files",
            headers={**drive_headers(token), "content-type": "application/json"},
            json={"name": name, "mimeType": DRIVE_FOLDER_MIME, "parents": [parent_id]},
            params={"fields": "id", "supportsAllDrives": "true"},
        )
        response.raise_for_status()
        return str(response.json()["id"])


def upload_drive_file(token: str, parent_id: str, path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    metadata = {"name": path.name, "parents": [parent_id]}
    with path.open("rb") as file_obj:
        files = {
            "metadata": (None, json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (path.name, file_obj, mime_type),
        }
        with httpx.Client(timeout=900) as client:
            response = client.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                headers=drive_headers(token),
                params={
                    "uploadType": "multipart",
                    "fields": "id,name,webViewLink,size,mimeType",
                    "supportsAllDrives": "true",
                },
                files=files,
            )
            response.raise_for_status()
            return response.json()


def list_drive_children(token: str, parent_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
    query = f"'{drive_query_literal(parent_id)}' in parents and trashed = false"
    fields = (
        "nextPageToken,files(id,name,mimeType,modifiedTime,size,webViewLink,"
        "parents,md5Checksum)"
    )
    files: list[dict[str, Any]] = []
    page_token: str | None = None
    with httpx.Client(timeout=120) as client:
        while True:
            response = client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=drive_headers(token),
                params={
                    "q": query,
                    "fields": fields,
                    "pageSize": str(page_size),
                    "pageToken": page_token,
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                },
            )
            response.raise_for_status()
            payload = response.json()
            files.extend(payload.get("files") or [])
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
    return files


def download_drive_file(token: str, file_id: str, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=900, follow_redirects=True) as client:
        with client.stream(
            "GET",
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=drive_headers(token),
            params={"alt": "media", "supportsAllDrives": "true"},
        ) as response:
            response.raise_for_status()
            bytes_written = 0
            with destination.open("wb") as file_obj:
                for chunk in response.iter_bytes(1024 * 1024):
                    file_obj.write(chunk)
                    bytes_written += len(chunk)
    return bytes_written


def export_drive_file(token: str, file_id: str, destination: Path, mime_type: str) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=900, follow_redirects=True) as client:
        with client.stream(
            "GET",
            f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
            headers=drive_headers(token),
            params={"mimeType": mime_type},
        ) as response:
            response.raise_for_status()
            bytes_written = 0
            with destination.open("wb") as file_obj:
                for chunk in response.iter_bytes(1024 * 1024):
                    file_obj.write(chunk)
                    bytes_written += len(chunk)
    return bytes_written


def archive_records(
    *,
    source_system: str,
    entity: str,
    sync_id: str,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    config = archive_config(env)
    now = datetime.now(timezone.utc)
    source_slug = slug(source_system)
    entity_slug = slug(entity)
    sync_slug = slug(sync_id)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    relative_dir = Path(source_slug) / entity_slug / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    archive_dir = (ROOT / config.local_dir / relative_dir).resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{stamp}_{sync_slug}"

    file_specs = [
        ("jsonl", archive_dir / f"{base_name}_raw.jsonl", write_jsonl),
        ("csv", archive_dir / f"{base_name}_clean.csv", write_csv),
        ("parquet", archive_dir / f"{base_name}_clean.parquet", write_parquet),
    ]
    files: list[dict[str, Any]] = []
    for file_format, path, writer in file_specs:
        writer(path, rows)
        files.append(
            {
                "format": file_format,
                "path": str(path),
                "relative_path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
                "drive": None,
            }
        )

    manifest = {
        "source_system": source_system,
        "entity": entity,
        "sync_id": sync_id,
        "row_count": len(rows),
        "archived_at": now.isoformat(),
        "metadata": metadata or {},
        "files": files,
    }
    manifest_path = archive_dir / f"{base_name}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    files.append(
        {
            "format": "manifest",
            "path": str(manifest_path),
            "relative_path": str(manifest_path.relative_to(ROOT)),
            "bytes": manifest_path.stat().st_size,
            "sha256": file_sha256(manifest_path),
            "drive": None,
        }
    )

    drive_error = None
    if config.provider == "google_drive" and config.drive_folder_id:
        try:
            token = drive_access_token(config)
            if token:
                parent_id = config.drive_folder_id
                for folder_name in relative_dir.parts:
                    parent_id = ensure_drive_folder(token, parent_id, folder_name)
                for file_info in files:
                    file_info["drive"] = upload_drive_file(token, parent_id, Path(file_info["path"]))
            else:
                drive_error = "Credencial Google nao configurada."
        except Exception as exc:
            drive_error = f"{type(exc).__name__}: {str(exc)[:300]}"

    result = {
        "source_system": source_system,
        "entity": entity,
        "sync_id": sync_id,
        "row_count": len(rows),
        "archive_dir": str(archive_dir),
        "relative_dir": str(relative_dir),
        "files": files,
        "drive_error": drive_error,
    }
    register_archive_catalog(result, metadata=metadata or {}, env=env)
    return result


def require_drive_archive(result: dict[str, Any], *, env: dict[str, str] | None = None) -> None:
    """Fail fast when Google Drive is the configured archive and upload did not complete."""
    config = archive_config(env)
    if config.provider != "google_drive":
        return
    values = env or load_env()
    fail_on_error = values.get("ARCHIVE_FAIL_ON_DRIVE_ERROR", "false").strip().lower() in {"1", "true", "yes"}
    if not fail_on_error:
        return
    if not config.drive_folder_id:
        raise RuntimeError("ARCHIVE_GOOGLE_DRIVE_FOLDER_ID nao configurado para archive no Google Drive.")
    if result.get("drive_error"):
        raise RuntimeError(f"Falha ao arquivar no Google Drive: {result['drive_error']}")

    missing = [
        file_info.get("relative_path") or file_info.get("path")
        for file_info in result.get("files", [])
        if not (file_info.get("drive") or {}).get("id")
    ]
    if missing:
        preview = ", ".join(str(item) for item in missing[:3])
        suffix = "..." if len(missing) > 3 else ""
        raise RuntimeError(f"Archive Google Drive incompleto. Arquivos sem drive_file_id: {preview}{suffix}")


def register_archive_catalog(result: dict[str, Any], *, metadata: dict[str, Any], env: dict[str, str] | None = None) -> None:
    values = env or load_env()
    try:
        with connect_database(values) as conn:
            with conn.cursor() as cur:
                for file_info in result["files"]:
                    drive = file_info.get("drive") or {}
                    cur.execute(
                        """
                        insert into public.data_archive_catalog(
                          source_system, entity, sync_id, storage_provider, storage_path,
                          storage_url, format, mime_type, row_count, byte_size, sha256, metadata
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        on conflict (storage_provider, storage_path)
                        do update set
                          storage_url = excluded.storage_url,
                          row_count = excluded.row_count,
                          byte_size = excluded.byte_size,
                          sha256 = excluded.sha256,
                          metadata = excluded.metadata,
                          archived_at = now()
                        """,
                        (
                            result["source_system"],
                            result["entity"],
                            result["sync_id"],
                            "google_drive" if drive else "local",
                            str(drive.get("id") or file_info["relative_path"]),
                            drive.get("webViewLink"),
                            file_info["format"],
                            drive.get("mimeType"),
                            result["row_count"],
                            file_info["bytes"],
                            file_info["sha256"],
                            json.dumps({**metadata, "drive_error": result.get("drive_error")}, ensure_ascii=False),
                        ),
                    )
                conn.commit()
    except BaseException:
        return
