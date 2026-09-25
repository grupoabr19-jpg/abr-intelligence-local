from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.api.data import (
    ATTENDANCE_FIELD_ALIASES,
    attendance_field,
    attendance_person_key,
    load_varejo_region_dimension,
    normalize_attendance_text,
    parse_attendance_datetime,
    parse_attendance_number,
)
from tools.apply_migrations import connect_database, load_env


def key_text(value: Any, fallback: str = "sem_valor") -> str:
    normalized = normalize_attendance_text(value)
    normalized = re.sub(r"[^A-Z0-9]+", "_", normalized).strip("_")
    return normalized.casefold() if normalized else fallback


def decimal_or_zero(value: Any) -> Decimal:
    parsed = parse_attendance_number(value)
    return parsed if parsed is not None else Decimal("0")


def payload_value(payload: dict[str, Any], *keys: str) -> Any:
    normalized = {normalize_attendance_text(key): value for key, value in payload.items()}
    for key in keys:
        value = normalized.get(normalize_attendance_text(key))
        if value not in (None, ""):
            return value
    return None


def status_type(pipeline: Any, stage: Any, status_id: Any) -> str:
    normalized_pipeline = normalize_attendance_text(pipeline)
    normalized_stage = normalize_attendance_text(stage)
    if normalized_pipeline == "FUNIL DE LIDERANCAS":
        return "lideranca"
    if normalized_stage == "COMUNICACAO INTERNA" or str(status_id or "").strip() == "109439252":
        return "interno"
    if normalized_stage == "VENDA GANHA":
        return "ganha"
    if normalized_stage == "VENDA PERDIDA":
        return "perdida"
    return "andamento"


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def load_active_staging(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        select source_id, payload_original, hash_registro, sync_id, imported_at
        from public.staging_dados
        where entidade = 'atendimento_kommo'
          and source_system = 'KOMMO_API'
          and ativo = true
        order by imported_at desc
        limit 100000
        """
    )
    return [
        {
            "source_id": row[0],
            "payload": row[1],
            "hash_registro": row[2],
            "sync_id": row[3],
            "imported_at": row[4],
        }
        for row in cur.fetchall()
        if isinstance(row[1], dict)
    ]


def refresh_dimensions(cur: Any, staging_rows: list[dict[str, Any]]) -> dict[str, int]:
    region_dimension = load_varejo_region_dimension(cur)
    regions = {
        row["regiao_polo"]: "ATACADO" if row["regiao_polo"] == "ATACADO" else "VAREJO"
        for row in region_dimension.values()
    }
    regions.setdefault("Sem cadastro", "INDEFINIDO")

    cur.executemany(
        """
        insert into public.dim_atendimento_regiao_polo(regiao_polo, canal, ativo, atualizado_em)
        values (%s, %s, true, now())
        on conflict (regiao_polo) do update
        set canal = excluded.canal,
            ativo = true,
            atualizado_em = now()
        """,
        [(region, channel) for region, channel in sorted(regions.items())],
    )

    collaborator_rows = []
    for key, row in region_dimension.items():
        collaborator_rows.append((key, row["colaborador"], row["funcao"], row["regiao_polo"], "cadastro_operacional"))

    for item in staging_rows:
        payload = item["payload"]
        owner = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["owner"]) or attendance_field(
            payload, ATTENDANCE_FIELD_ALIASES["first_responder"]
        )
        key = attendance_person_key(owner)
        if key and key not in region_dimension:
            collaborator_rows.append((key, str(owner).strip(), "Sem cadastro", "Sem cadastro", "kommo_sem_mapeamento"))

    collaborator_rows = sorted({row[0]: row for row in collaborator_rows}.values(), key=lambda row: row[1])
    cur.executemany(
        """
        insert into public.dim_atendimento_colaborador(
          colaborador_key, nome, funcao, regiao_polo, origem, ativo, atualizado_em
        )
        values (%s, %s, %s, %s, %s, true, now())
        on conflict (colaborador_key) do update
        set nome = excluded.nome,
            funcao = excluded.funcao,
            regiao_polo = excluded.regiao_polo,
            origem = excluded.origem,
            ativo = true,
            atualizado_em = now()
        """,
        collaborator_rows,
    )

    cur.execute(
        """
        select kommo_pipeline_id, name, raw_hash, sync_id
        from public.raw_kommo_pipelines
        where ativo = true
        """
    )
    pipeline_rows = [(row[0], row[1] or str(row[0]), row[2], row[3]) for row in cur.fetchall()]
    for item in staging_rows:
        payload = item["payload"]
        pipeline_id = payload_value(payload, "Pipeline ID", "pipeline_id")
        pipeline_name = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["pipeline"])
        if pipeline_id:
            pipeline_rows.append((int(pipeline_id), str(pipeline_name or pipeline_id), item["hash_registro"], item["sync_id"]))
    pipeline_rows = sorted({row[0]: row for row in pipeline_rows}.values(), key=lambda row: row[0])
    cur.executemany(
        """
        insert into public.dim_kommo_pipeline(pipeline_id, nome, raw_hash, sync_id, ativo, atualizado_em)
        values (%s, %s, %s, %s, true, now())
        on conflict (pipeline_id) do update
        set nome = excluded.nome,
            raw_hash = excluded.raw_hash,
            sync_id = excluded.sync_id,
            ativo = true,
            atualizado_em = now()
        """,
        pipeline_rows,
    )

    cur.execute(
        """
        select kommo_status_id, kommo_pipeline_id, name, raw_hash, sync_id
        from public.raw_kommo_statuses
        where ativo = true
        """
    )
    status_rows = [
        (row[0], row[1], row[2] or str(row[0]), status_type(None, row[2], row[0]), row[3], row[4])
        for row in cur.fetchall()
    ]
    for item in staging_rows:
        payload = item["payload"]
        status_id = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["status_id"])
        pipeline_id = payload_value(payload, "Pipeline ID", "pipeline_id")
        stage = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["stage"])
        pipeline = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["pipeline"])
        if status_id:
            status_rows.append(
                (
                    int(status_id),
                    int(pipeline_id) if pipeline_id else None,
                    str(stage or status_id),
                    status_type(pipeline, stage, status_id),
                    item["hash_registro"],
                    item["sync_id"],
                )
            )
    status_rows = sorted({row[0]: row for row in status_rows}.values(), key=lambda row: row[0])
    cur.executemany(
        """
        insert into public.dim_kommo_status(status_id, pipeline_id, nome, tipo_status, raw_hash, sync_id, ativo, atualizado_em)
        values (%s, %s, %s, %s, %s, %s, true, now())
        on conflict (status_id) do update
        set pipeline_id = excluded.pipeline_id,
            nome = excluded.nome,
            tipo_status = excluded.tipo_status,
            raw_hash = excluded.raw_hash,
            sync_id = excluded.sync_id,
            ativo = true,
            atualizado_em = now()
        """,
        status_rows,
    )

    origins = {}
    for item in staging_rows:
        payload = item["payload"]
        origin = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["origin"]) or "Sem origem"
        origins[key_text(origin, "sem_origem")] = str(origin)
    cur.executemany(
        """
        insert into public.dim_atendimento_origem(origem_key, origem, ativo, atualizado_em)
        values (%s, %s, true, now())
        on conflict (origem_key) do update
        set origem = excluded.origem,
            ativo = true,
            atualizado_em = now()
        """,
        sorted(origins.items()),
    )

    return {
        "regioes": len(regions),
        "colaboradores": len(collaborator_rows),
        "pipelines": len(pipeline_rows),
        "status_kommo": len(status_rows),
        "origens": len(origins),
    }


def refresh_facts(cur: Any, staging_rows: list[dict[str, Any]]) -> dict[str, int]:
    lead_rows = []
    sla_rows = []
    followup_rows = []
    missing_owner = 0
    missing_sla = 0
    excluded = 0

    for item in staging_rows:
        payload = item["payload"]
        lead_id = str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["lead_id"]) or "").strip()
        if not lead_id:
            continue
        owner = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["owner"]) or attendance_field(
            payload, ATTENDANCE_FIELD_ALIASES["first_responder"]
        )
        collaborator_key = attendance_person_key(owner)
        if not collaborator_key:
            collaborator_key = None
            missing_owner += 1
        pipeline = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["pipeline"])
        stage = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["stage"])
        status_id = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["status_id"])
        pipeline_id = payload_value(payload, "Pipeline ID", "pipeline_id")
        kind = status_type(pipeline, stage, status_id)
        is_excluded = kind in {"interno", "lideranca"}
        if is_excluded:
            excluded += 1
        first_contact = parse_attendance_datetime(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["first_contact"]))
        first_response = parse_attendance_datetime(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["first_response"]))
        wait = parse_attendance_number(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["wait_minutes"]))
        if wait is None and first_contact and first_response:
            wait = Decimal(str(max((first_response - first_contact).total_seconds() / 60, 0)))
        sla_valid = bool(first_contact and first_response and wait is not None and wait >= 0)
        if not sla_valid:
            missing_sla += 1
        next_task = parse_attendance_datetime(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["next_task"]))
        origin = attendance_field(payload, ATTENDANCE_FIELD_ALIASES["origin"]) or "Sem origem"
        situacao = str(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["situation"]) or "Aberto")
        normalized_situation = normalize_attendance_text(situacao)

        lead_rows.append(
            (
                lead_id,
                payload_value(payload, "Nome do lead", "Lead", "name"),
                iso(parse_attendance_datetime(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["created_at"]))),
                iso(parse_attendance_datetime(payload_value(payload, "Atualizado em", "updated_at"))),
                iso(parse_attendance_datetime(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["closed_at"]))),
                int(pipeline_id) if pipeline_id else None,
                int(status_id) if status_id else None,
                collaborator_key,
                key_text(origin, "sem_origem"),
                situacao,
                decimal_or_zero(attendance_field(payload, ATTENDANCE_FIELD_ALIASES["value"])),
                normalized_situation == "ABERTO" and not is_excluded,
                kind == "ganha" and not is_excluded,
                kind == "perdida" and not is_excluded,
                is_excluded,
                kind if is_excluded else None,
                item["hash_registro"],
                item["sync_id"],
            )
        )
        sla_rows.append(
            (
                lead_id,
                iso(first_contact),
                iso(first_response),
                wait,
                sla_valid,
                bool(sla_valid and wait is not None and wait <= 5),
                bool(sla_valid and wait is not None and wait <= 15),
                bool(first_contact and not first_response),
            )
        )
        followup_rows.append((lead_id, iso(next_task), bool(next_task)))

    cur.executemany(
        """
        insert into public.fato_atendimento_lead(
          lead_id, nome_lead, created_at_kommo, updated_at_kommo, closed_at_kommo,
          pipeline_id, status_id, colaborador_key, origem_key, situacao, valor,
          is_aberto, is_ganho, is_perdido, excluido, motivo_exclusao, raw_hash, sync_id, refreshed_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (lead_id) do update
        set nome_lead = excluded.nome_lead,
            created_at_kommo = excluded.created_at_kommo,
            updated_at_kommo = excluded.updated_at_kommo,
            closed_at_kommo = excluded.closed_at_kommo,
            pipeline_id = excluded.pipeline_id,
            status_id = excluded.status_id,
            colaborador_key = excluded.colaborador_key,
            origem_key = excluded.origem_key,
            situacao = excluded.situacao,
            valor = excluded.valor,
            is_aberto = excluded.is_aberto,
            is_ganho = excluded.is_ganho,
            is_perdido = excluded.is_perdido,
            excluido = excluded.excluido,
            motivo_exclusao = excluded.motivo_exclusao,
            raw_hash = excluded.raw_hash,
            sync_id = excluded.sync_id,
            refreshed_at = now()
        """,
        lead_rows,
    )
    cur.executemany(
        """
        insert into public.fato_atendimento_sla(
          lead_id, primeiro_contato_em, primeira_resposta_em, espera_minutos,
          sla_valido, sla_5_min, sla_15_min, sem_resposta, refreshed_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, now())
        on conflict (lead_id) do update
        set primeiro_contato_em = excluded.primeiro_contato_em,
            primeira_resposta_em = excluded.primeira_resposta_em,
            espera_minutos = excluded.espera_minutos,
            sla_valido = excluded.sla_valido,
            sla_5_min = excluded.sla_5_min,
            sla_15_min = excluded.sla_15_min,
            sem_resposta = excluded.sem_resposta,
            refreshed_at = now()
        """,
        sla_rows,
    )
    cur.executemany(
        """
        insert into public.fato_atendimento_followup(lead_id, proxima_tarefa_em, tem_followup, refreshed_at)
        values (%s, %s, %s, now())
        on conflict (lead_id) do update
        set proxima_tarefa_em = excluded.proxima_tarefa_em,
            tem_followup = excluded.tem_followup,
            refreshed_at = now()
        """,
        followup_rows,
    )

    quality_rows = [
        ("leads_sem_colaborador", "warning", missing_owner, {}),
        ("leads_sem_sla_calculavel", "warning", missing_sla, {}),
        ("leads_excluidos_regra_operacional", "info", excluded, {}),
    ]
    cur.executemany(
        """
        insert into public.atendimento_data_quality(regra, severidade, total, detalhes)
        values (%s, %s, %s, %s::jsonb)
        """,
        [(rule, severity, total, json.dumps(details, ensure_ascii=False)) for rule, severity, total, details in quality_rows],
    )
    return {
        "leads_processados": len(lead_rows),
        "missing_owner": missing_owner,
        "missing_sla": missing_sla,
        "excluded": excluded,
    }


def refresh() -> dict[str, Any]:
    sync_id = f"atendimento_refresh_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into public.atendimento_refresh_runs(sync_id, status) values (%s, 'processando')",
                (sync_id,),
            )
            staging_rows = load_active_staging(cur)
            dimensions = refresh_dimensions(cur, staging_rows)
            facts = refresh_facts(cur, staging_rows)
            cur.execute(
                """
                update public.atendimento_refresh_runs
                set status = 'sucesso',
                    finished_at = now(),
                    leads_processados = %s,
                    colaboradores = %s,
                    regioes = %s,
                    pipelines = %s,
                    status_kommo = %s,
                    origens = %s
                where sync_id = %s
                """,
                (
                    facts["leads_processados"],
                    dimensions["colaboradores"],
                    dimensions["regioes"],
                    dimensions["pipelines"],
                    dimensions["status_kommo"],
                    dimensions["origens"],
                    sync_id,
                ),
            )
            conn.commit()
    return {"sync_id": sync_id, **dimensions, **facts}


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualiza dimensoes e fatos do modulo Atendimento.")
    parser.parse_args()
    print(json.dumps(refresh(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
