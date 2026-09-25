from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apply_migrations import connect_database, load_env


def key(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text or "SEMVALOR"


def refresh() -> dict[str, Any]:
    batch_id = f"official_atendimento_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    env = load_env()
    with connect_database(env) as conn:
        with conn.cursor() as cur:
            cur.execute("truncate table public.colaboradores_nao_mapeados")
            cur.execute(
                """
                insert into public.dim_funil(id_funil, nome_funil, source, ativo)
                select pipeline_id::text, nome, 'KOMMO', true
                from public.dim_kommo_pipeline
                on conflict (id_funil) do update
                set nome_funil = excluded.nome_funil,
                    ativo = true
                """
            )
            cur.execute(
                """
                insert into public.dim_etapa(id_etapa, id_funil, nome_original, nome_normalizado, tipo_etapa, ativo)
                select
                  s.status_id::text,
                  s.pipeline_id::text,
                  s.nome,
                  upper(unaccent(trim(s.nome))),
                  s.tipo_status,
                  true
                from public.dim_kommo_status s
                on conflict (id_etapa) do update
                set id_funil = excluded.id_funil,
                    nome_original = excluded.nome_original,
                    nome_normalizado = excluded.nome_normalizado,
                    tipo_etapa = excluded.tipo_etapa,
                    ativo = true
                """
            )
            cur.execute(
                """
                insert into public.fact_kommo_leads(
                  lead_id, created_at, closed_at, pipeline, stage_original, stage_normalized, status,
                  responsible_id, first_responder_id, source, segment, temperature, crm_value,
                  first_contact_at, first_human_response_at, wait_minutes, last_interaction_at, next_task_at,
                  contact_id, company_id, id_colaborador, origem_payload_hash, batch_id, refreshed_at
                )
                select
                  f.lead_id,
                  f.created_at_kommo,
                  f.closed_at_kommo,
                  p.nome,
                  s.nome,
                  upper(unaccent(trim(coalesce(s.nome, '')))),
                  case
                    when f.is_ganho then 'won'
                    when f.is_perdido then 'lost'
                    when f.is_aberto then 'open'
                    else lower(coalesce(f.situacao, 'unknown'))
                  end,
                  f.colaborador_key,
                  f.colaborador_key,
                  o.origem,
                  null,
                  null,
                  f.valor,
                  sla.primeiro_contato_em,
                  sla.primeira_resposta_em,
                  sla.espera_minutos,
                  f.updated_at_kommo,
                  fo.proxima_tarefa_em,
                  null,
                  null,
                  c.id_colaborador,
                  f.raw_hash,
                  %s,
                  now()
                from public.fato_atendimento_lead f
                left join public.dim_kommo_pipeline p on p.pipeline_id = f.pipeline_id
                left join public.dim_kommo_status s on s.status_id = f.status_id
                left join public.dim_atendimento_origem o on o.origem_key = f.origem_key
                left join public.fato_atendimento_sla sla on sla.lead_id = f.lead_id
                left join public.fato_atendimento_followup fo on fo.lead_id = f.lead_id
                left join public.dim_colaborador c on c.id_colaborador = f.colaborador_key
                where f.excluido = false
                on conflict (lead_id) do update
                set created_at = excluded.created_at,
                    closed_at = excluded.closed_at,
                    pipeline = excluded.pipeline,
                    stage_original = excluded.stage_original,
                    stage_normalized = excluded.stage_normalized,
                    status = excluded.status,
                    responsible_id = excluded.responsible_id,
                    first_responder_id = excluded.first_responder_id,
                    source = excluded.source,
                    segment = excluded.segment,
                    temperature = excluded.temperature,
                    crm_value = excluded.crm_value,
                    first_contact_at = excluded.first_contact_at,
                    first_human_response_at = excluded.first_human_response_at,
                    wait_minutes = excluded.wait_minutes,
                    last_interaction_at = excluded.last_interaction_at,
                    next_task_at = excluded.next_task_at,
                    id_colaborador = excluded.id_colaborador,
                    origem_payload_hash = excluded.origem_payload_hash,
                    batch_id = excluded.batch_id,
                    refreshed_at = now()
                """,
                (batch_id,),
            )
            cur.execute(
                """
                insert into public.fact_kommo_tasks(
                  task_id, lead_id, responsible_id, task_type, complete_till, is_completed,
                  raw_payload_hash, batch_id, refreshed_at
                )
                select
                  kommo_task_id::text,
                  entity_id::text,
                  responsible_user_id::text,
                  entity_type,
                  complete_till_kommo,
                  is_completed,
                  raw_hash,
                  %s,
                  now()
                from public.raw_kommo_tasks
                where ativo = true
                on conflict (task_id) do update
                set lead_id = excluded.lead_id,
                    responsible_id = excluded.responsible_id,
                    task_type = excluded.task_type,
                    complete_till = excluded.complete_till,
                    is_completed = excluded.is_completed,
                    raw_payload_hash = excluded.raw_payload_hash,
                    batch_id = excluded.batch_id,
                    refreshed_at = now()
                """,
                (batch_id,),
            )
            cur.execute(
                """
                insert into public.fact_kommo_interacoes(
                  interaction_id, lead_id, interaction_type, created_at, created_by,
                  raw_payload_hash, batch_id, refreshed_at
                )
                select
                  kommo_event_id,
                  entity_id::text,
                  event_type,
                  created_at_kommo,
                  created_by::text,
                  raw_hash,
                  %s,
                  now()
                from public.raw_kommo_events e
                where e.ativo = true
                  and exists (
                    select 1 from public.fact_kommo_leads f
                    where f.lead_id = e.entity_id::text
                  )
                on conflict (interaction_id) do update
                set lead_id = excluded.lead_id,
                    interaction_type = excluded.interaction_type,
                    created_at = excluded.created_at,
                    created_by = excluded.created_by,
                    raw_payload_hash = excluded.raw_payload_hash,
                    batch_id = excluded.batch_id,
                    refreshed_at = now()
                """
                ,
                (batch_id,),
            )
            cur.execute(
                """
                insert into public.fact_occurrences(
                  occurrence_id, type, source, lead_id, responsible_id, opened_at, status, severity, details, refreshed_at
                )
                select
                  'lead_sem_followup:' || f.lead_id,
                  'Lead sem follow-up',
                  'KOMMO',
                  f.lead_id,
                  f.colaborador_key,
                  coalesce(f.created_at_kommo, now()),
                  'aberta',
                  'media',
                  jsonb_build_object('motivo', 'Lead aberto sem proxima tarefa'),
                  now()
                from public.fato_atendimento_lead f
                left join public.fato_atendimento_followup fo on fo.lead_id = f.lead_id
                where f.excluido = false and f.is_aberto = true and coalesce(fo.tem_followup, false) = false
                on conflict (occurrence_id) do update
                set status = excluded.status,
                    responsible_id = excluded.responsible_id,
                    details = excluded.details,
                    refreshed_at = now()
                """
            )
            cur.execute(
                """
                insert into public.fact_occurrences(
                  occurrence_id, type, source, lead_id, responsible_id, opened_at, status, severity, details, refreshed_at
                )
                select
                  'lead_sem_acao:' || f.lead_id,
                  'Lead sem primeira acao',
                  'KOMMO',
                  f.lead_id,
                  f.colaborador_key,
                  coalesce(sla.primeiro_contato_em, f.created_at_kommo, now()),
                  'aberta',
                  'alta',
                  jsonb_build_object('motivo', 'Lead criado sem primeira acao humana registrada'),
                  now()
                from public.fato_atendimento_lead f
                join public.fato_atendimento_sla sla on sla.lead_id = f.lead_id
                where f.excluido = false and sla.sem_resposta = true
                on conflict (occurrence_id) do update
                set status = excluded.status,
                    responsible_id = excluded.responsible_id,
                    details = excluded.details,
                    refreshed_at = now()
                """
            )
            cur.execute(
                """
                insert into public.colaboradores_nao_mapeados(nome_origem, source, total_registros, last_seen_at)
                select coalesce(c.nome, f.colaborador_key, 'SEM COLABORADOR'), 'KOMMO', count(*), now()
                from public.fato_atendimento_lead f
                left join public.dim_atendimento_colaborador c on c.colaborador_key = f.colaborador_key
                where f.excluido = false
                  and not exists (
                    select 1 from public.dim_colaborador dc where dc.id_colaborador = f.colaborador_key
                  )
                group by 1
                on conflict (nome_origem) do update
                set total_registros = excluded.total_registros,
                    last_seen_at = now()
                """
            )
            cur.execute(
                """
                insert into public.data_quality_alerts(batch_name, rule, severity, total, details)
                select 'BATCH_02_03', 'colaboradores_nao_mapeados', 'warning', count(*), '{}'::jsonb
                from public.colaboradores_nao_mapeados
                """
            )
            cur.execute("select count(*) from public.fact_kommo_leads")
            leads = int(cur.fetchone()[0] or 0)
            cur.execute("select count(*) from public.fact_kommo_tasks")
            tasks = int(cur.fetchone()[0] or 0)
            cur.execute("select count(*) from public.fact_kommo_interacoes")
            interactions = int(cur.fetchone()[0] or 0)
            cur.execute("select count(*) from public.fact_occurrences")
            occurrences = int(cur.fetchone()[0] or 0)
            cur.execute("select count(*) from public.colaboradores_nao_mapeados")
            unmapped = int(cur.fetchone()[0] or 0)
            conn.commit()
    return {
        "batch_id": batch_id,
        "fact_kommo_leads": leads,
        "fact_kommo_tasks": tasks,
        "fact_kommo_interacoes": interactions,
        "fact_occurrences": occurrences,
        "colaboradores_nao_mapeados": unmapped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualiza contrato oficial do modulo Atendimento.")
    parser.parse_args()
    print(json.dumps(refresh(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
