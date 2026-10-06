from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from fastapi import HTTPException, status
from psycopg.types.json import Json

from tools.apply_migrations import connect_core_database, load_env


SOURCE_ID_KEYS = (
    "id",
    "Id",
    "ID",
    "docEntry",
    "DocEntry",
    "pedido",
    "Pedido",
    "numero",
    "Numero",
    "codigo",
    "Codigo",
    "Código",
)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def source_id_from_row(row: dict[str, Any], fallback: str) -> str:
    for key in SOURCE_ID_KEYS:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return fallback


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ingest_collector_payload(payload: dict[str, Any], provided_key: str | None) -> dict[str, Any]:
    env = load_env()
    collector_key = env.get("ABR_COLLECTOR_KEY") or env.get("ASTER_COLLECTOR_INGEST_KEY") or ""
    if not collector_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ABR_COLLECTOR_KEY nao configurada no backend.",
        )
    if not provided_key or provided_key != collector_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Chave do coletor invalida.")

    fonte_id = str(payload.get("fonte_id") or "").strip()
    if not fonte_id:
        raise HTTPException(status_code=400, detail="fonte_id e obrigatorio.")

    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise HTTPException(status_code=400, detail="rows deve conter ao menos um objeto.")

    rows = [row for row in raw_rows if isinstance(row, dict)][:1000]
    if not rows:
        raise HTTPException(status_code=400, detail="Nenhuma linha valida para ingestao.")

    sync_id = str(payload.get("sync_id") or "").strip()
    if not sync_id:
        sync_id = f"ASTER-{time.strftime('%Y%m%d%H%M%S')}-{sha256_hex(str(time.time()))[:6].upper()}"
    entidade = str(payload.get("entidade") or "aster_relatorio").strip() or "aster_relatorio"
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    inserted = 0
    with connect_core_database(env) as conn:
        with conn.cursor() as cur:
            for index, row in enumerate(rows):
                hash_registro = sha256_hex(f"{fonte_id}|{entidade}|{stable_json(row)}")
                cur.execute(
                    """
                    insert into public.staging_dados(
                      fonte_id,
                      source_system,
                      source_id,
                      entidade,
                      payload_original,
                      dados_transformados,
                      sync_id,
                      hash_registro,
                      status_validacao,
                      erro_validacao,
                      tabela_destino,
                      coleta_metadata,
                      ativo
                    )
                    values (
                      %s::uuid,
                      'ASTER_CHROME',
                      %s,
                      %s,
                      %s,
                      %s,
                      %s,
                      %s,
                      'pendente',
                      null,
                      null,
                      %s,
                      true
                    )
                    on conflict (fonte_id, hash_registro) do nothing
                    returning id
                    """,
                    (
                        fonte_id,
                        source_id_from_row(row, f"row-{index + 1}"),
                        entidade,
                        Json(row),
                        Json(row),
                        sync_id,
                        hash_registro,
                        Json(metadata),
                    ),
                )
                if cur.fetchone():
                    inserted += 1

            cur.execute(
                """
                select registros_lidos, registros_inseridos, registros_atualizados, registros_erro
                  from public.historico_importacoes
                 where sync_id = %s
                """,
                (sync_id,),
            )
            existing = cur.fetchone()
            registros_lidos = int(existing[0] if existing else 0) + len(rows)
            registros_inseridos = int(existing[1] if existing else 0) + inserted
            registros_atualizados = int(existing[2] if existing else 0)
            registros_erro = int(existing[3] if existing else 0)

            cur.execute(
                """
                insert into public.historico_importacoes(
                  sync_id,
                  fonte_id,
                  entidade,
                  status,
                  registros_lidos,
                  registros_inseridos,
                  registros_atualizados,
                  registros_erro,
                  origem_arquivo,
                  log,
                  iniciado_em,
                  finalizado_em
                )
                values (
                  %s,
                  %s::uuid,
                  %s,
                  'sucesso',
                  %s,
                  %s,
                  %s,
                  %s,
                  'ASTER_CHROME',
                  %s,
                  now(),
                  now()
                )
                on conflict (sync_id) do update set
                  status = excluded.status,
                  registros_lidos = excluded.registros_lidos,
                  registros_inseridos = excluded.registros_inseridos,
                  registros_atualizados = excluded.registros_atualizados,
                  registros_erro = excluded.registros_erro,
                  log = excluded.log,
                  finalizado_em = excluded.finalizado_em
                """,
                (
                    sync_id,
                    fonte_id,
                    entidade,
                    registros_lidos,
                    registros_inseridos,
                    registros_atualizados,
                    registros_erro,
                    f"Ingestao Aster acumulada com {registros_lidos} registros recebidos.",
                ),
            )
        conn.commit()

    return {
        "sucesso": True,
        "sync_id": sync_id,
        "recebidos": len(rows),
        "inseridos": inserted,
        "recebidos_acumulado": registros_lidos,
    }
