from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from tools.apply_migrations import connect_crm_database, connect_database, load_env


ROOT = Path(__file__).resolve().parents[2]

ASTER_REFRESH_REPORTS = (
    "D0A4D301",  # Analise de Vendas por Item
    "0F75E84D",  # Resumo Comercial
    "AB439998",  # Vendas por Indicacao
    "027051BD",  # Segmentacao de Lead
    "804C04C1",  # Estoque
    "6630A54D",  # Estoque Disponivel
    "DBF2AB0E",  # Estoque WMS
    "CAF55C1D",  # Ultimo preco de venda
    "C1A4D279",  # Ocorrencias transporte
)

PENDING_MARKET_SOURCES = (
    "ABRAMAT",
    "ANFAVEA",
)

STALE_REFRESH_MINUTES = 30
AUTO_REFRESH_CHECK_SECONDS = int(os.environ.get("ABR_AUTO_REFRESH_CHECK_SECONDS", "1800") or "1800")
AUTO_REFRESH_START_DELAY_SECONDS = int(os.environ.get("ABR_AUTO_REFRESH_START_DELAY_SECONDS", "20") or "20")


RefreshStatus = Literal["queued", "running", "succeeded", "partial", "failed", "skipped"]


@dataclass
class RefreshStep:
    key: str
    label: str
    status: RefreshStatus = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    return_code: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class DashboardRefreshJob:
    job_id: str
    mode: Literal["auto", "manual"]
    status: RefreshStatus
    date_from: str
    date_to: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    message: str = ""
    steps: list[RefreshStep] = field(default_factory=list)


class DashboardRefreshManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._current_job: DashboardRefreshJob | None = None
        self._history: list[DashboardRefreshJob] = []
        self._daily_checked_for: str | None = None
        self._auto_loop_started = False

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            current = self.serialize_job(self._current_job) if self._current_job else None
            history = [self.serialize_job(item) for item in self._history[:5]]
        stored = await asyncio.to_thread(self._stored_jobs)
        if not current:
            current = stored.get("current")
        if stored.get("history"):
            history = stored["history"]
        sources = await asyncio.to_thread(self._source_freshness)
        return {"current": current, "history": history, "sources": sources}

    async def ensure_daily_refresh(self, date_from: date | None, date_to: date | None) -> DashboardRefreshJob | None:
        today = date.today()
        today_key = today.isoformat()
        async with self._lock:
            self._daily_checked_for = today_key
            if self._current_job and self._current_job.status in {"queued", "running"}:
                return self._current_job

        fresh = await asyncio.to_thread(self._is_fresh_today)
        if fresh:
            return None
        if date_from is None and date_to is None:
            date_from, date_to = self._default_auto_refresh_range()
        return await self.start_refresh(mode="auto", date_from=date_from, date_to=date_to, force=False)

    async def run_auto_refresh_loop(self) -> None:
        async with self._lock:
            if self._auto_loop_started:
                return
            self._auto_loop_started = True
        await asyncio.sleep(max(AUTO_REFRESH_START_DELAY_SECONDS, 0))
        while True:
            try:
                await self.ensure_daily_refresh(date_from=None, date_to=None)
            except Exception:
                pass
            await asyncio.sleep(max(AUTO_REFRESH_CHECK_SECONDS, 300))

    async def start_refresh(
        self,
        *,
        mode: Literal["auto", "manual"],
        date_from: date | None,
        date_to: date | None,
        force: bool,
    ) -> DashboardRefreshJob:
        if mode == "auto" and date_from is None and date_to is None:
            date_from, date_to = self._default_auto_refresh_range()
        start = date_from or date(date.today().year, 1, 1)
        end = date_to or date.today()
        await asyncio.to_thread(self._mark_stale_jobs)
        stored = await asyncio.to_thread(self._stored_jobs)
        async with self._lock:
            if self._current_job and self._current_job.status in {"queued", "running"}:
                return self._current_job
            if stored.get("current"):
                return self._job_from_payload(stored["current"])

            job = DashboardRefreshJob(
                job_id=str(uuid.uuid4()),
                mode=mode,
                status="queued",
                date_from=start.isoformat(),
                date_to=end.isoformat(),
                created_at=self._now(),
                message="Atualizacao na fila.",
                steps=self._build_steps(),
            )
            self._current_job = job
            self._history.insert(0, job)
            self._history = self._history[:10]
        await asyncio.to_thread(self._persist_job, job)
        asyncio.create_task(self._run_job(job.job_id))
        return job

    async def _run_job(self, job_id: str) -> None:
        job = await self._get_job(job_id)
        if not job:
            return
        await self._update_job(job_id, status="running", started_at=self._now(), message="Atualizando fontes de dados.")

        failures = 0
        for index, step in enumerate(job.steps):
            if step.status == "skipped":
                continue
            await self._update_step(job_id, index, status="running", started_at=self._now())
            command = self._command_for_step(step.key, job)
            if not command:
                await self._update_step(job_id, index, status="skipped", finished_at=self._now())
                continue

            result = await self._run_command(command, timeout_seconds=self._timeout_for_step(step.key))
            status: RefreshStatus = "succeeded" if result["return_code"] == 0 else "failed"
            if status == "failed":
                failures += 1
            await self._update_step(
                job_id,
                index,
                status=status,
                finished_at=self._now(),
                return_code=result["return_code"],
                stdout_tail=result["stdout_tail"],
                stderr_tail=result["stderr_tail"],
                result=result["parsed_stdout"],
                error=result["error"],
            )

        final_status: RefreshStatus = "succeeded" if failures == 0 else "partial"
        if failures == len([step for step in job.steps if step.status != "skipped"]):
            final_status = "failed"
        await self._update_job(
            job_id,
            status=final_status,
            finished_at=self._now(),
            message="Atualizacao concluida." if final_status == "succeeded" else "Atualizacao concluida com pendencias.",
        )

    def _build_steps(self) -> list[RefreshStep]:
        steps = [
            RefreshStep("market_registry", "Mercado: verificar fontes configuradas"),
            RefreshStep("market_api", "Mercado API: BCB e IBGE"),
            RefreshStep("market_aneel", "Mercado ANEEL: geracao fotovoltaica"),
            RefreshStep("market_world_bank", "Mercado World Bank: contexto macro"),
            RefreshStep("market_obrasgov", "Mercado ObrasGov: projetos publicos"),
            RefreshStep("market_comex", "Mercado Comex: importacoes por NCM aprovado"),
            RefreshStep("market_gov", "Mercado governo: CAGED e PNCP configurados"),
            RefreshStep("market_public", "Mercado publico: Aco Brasil, CNI e INDA"),
            RefreshStep("kommo_collect", "Kommo API: leads, tarefas e eventos"),
            RefreshStep("atendimento_facts", "Atendimento: fatos, SLA e rankings"),
            RefreshStep("atendimento_contract", "Atendimento: contrato oficial"),
            RefreshStep("drive_spreadsheets", "Google Drive Archive: planilhas novas"),
        ]
        for query_id in ASTER_REFRESH_REPORTS:
            steps.append(RefreshStep(f"aster_{query_id}", f"Aster ERP: relatorio {query_id}"))
        steps.append(RefreshStep("aster_sales_fact", "Aster ERP: compactar vendas para dashboard"))
        steps.append(RefreshStep("sales_cache", "Dashboard comercial: recalcular cache"))
        steps.append(
            RefreshStep(
                "pending_market_collectors",
                "Fontes parametrizadas sem coletor ativo: " + ", ".join(PENDING_MARKET_SOURCES),
                status="skipped",
            )
        )
        return steps

    def _command_for_step(self, key: str, job: DashboardRefreshJob) -> list[str] | None:
        if key == "market_registry":
            return [sys.executable, str(ROOT / "tools" / "refresh_market_source_registry.py")]
        if key == "market_api":
            return [
                sys.executable,
                str(ROOT / "tools" / "collect_market_api_sources.py"),
                "--source",
                "all",
                "--date-from",
                job.date_from,
                "--date-to",
                job.date_to,
            ]
        if key == "market_comex":
            return [sys.executable, str(ROOT / "tools" / "collect_market_comex.py")]
        if key == "market_aneel":
            return [sys.executable, str(ROOT / "tools" / "collect_market_aneel.py")]
        if key == "market_world_bank":
            return [sys.executable, str(ROOT / "tools" / "collect_market_world_bank.py")]
        if key == "market_obrasgov":
            return [sys.executable, str(ROOT / "tools" / "collect_market_obrasgov.py")]
        if key == "market_gov":
            return [sys.executable, str(ROOT / "tools" / "collect_market_gov_sources.py"), "--source", "all"]
        if key == "market_public":
            return [sys.executable, str(ROOT / "tools" / "collect_market_sources.py"), "--source", "all"]
        if key == "kommo_collect":
            return [
                sys.executable,
                str(ROOT / "tools" / "collect_kommo_attendance.py"),
                "--date-from",
                job.date_from,
                "--date-to",
                job.date_to,
            ]
        if key == "atendimento_facts":
            return [sys.executable, str(ROOT / "tools" / "refresh_atendimento_facts.py")]
        if key == "atendimento_contract":
            return [sys.executable, str(ROOT / "tools" / "refresh_atendimento_official_contract.py")]
        if key == "drive_spreadsheets":
            return [sys.executable, str(ROOT / "tools" / "collect_drive_spreadsheets.py")]
        if key.startswith("aster_"):
            query_id = key.removeprefix("aster_")
            if key == "aster_sales_fact":
                return [sys.executable, str(ROOT / "tools" / "refresh_aster_sales_fact.py")]
            return [
                sys.executable,
                str(ROOT / "tools" / "aster_live_execute_ingest.py"),
                "--query-id",
                query_id,
                "--date-from",
                job.date_from,
                "--date-to",
                job.date_to,
                "--timeout-seconds",
                "900",
            ]
        if key == "sales_cache":
            return [
                sys.executable,
                str(ROOT / "tools" / "refresh_dashboard_sales_cache.py"),
                "--date-from",
                job.date_from,
                "--date-to",
                job.date_to,
            ]
        return None

    @staticmethod
    def _timeout_for_step(key: str) -> int:
        if key == "market_aneel":
            return 1_200
        if key == "aster_sales_fact":
            return 600
        if key.startswith("aster_"):
            return 1_000
        if key == "kommo_collect":
            return 600
        if key == "drive_spreadsheets":
            return 1_200
        return 300

    async def _run_command(self, command: list[str], timeout_seconds: int) -> dict[str, Any]:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return {
                "return_code": process.returncode,
                "stdout_tail": stdout[-6000:],
                "stderr_tail": stderr[-6000:],
                "parsed_stdout": self._parse_last_json(stdout),
                "error": None if process.returncode == 0 else (stderr or stdout)[-2000:],
            }
        except asyncio.TimeoutError:
            if "process" in locals() and process.returncode is None:
                process.kill()
                try:
                    await process.communicate()
                except Exception:
                    pass
            return {
                "return_code": -1,
                "stdout_tail": "",
                "stderr_tail": "",
                "parsed_stdout": None,
                "error": f"Timeout apos {timeout_seconds}s.",
            }
        except Exception as exc:
            return {
                "return_code": -1,
                "stdout_tail": "",
                "stderr_tail": "",
                "parsed_stdout": None,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def _is_fresh_today(self) -> bool:
        freshness = self._source_freshness()
        core = [item for item in freshness if item["required_for_daily"]]
        return bool(core) and all(item["updated_today"] for item in core)

    @staticmethod
    def _default_auto_refresh_range() -> tuple[date, date]:
        yesterday = date.today() - timedelta(days=1)
        return date(yesterday.year, 1, 1), yesterday

    def _source_freshness(self) -> list[dict[str, Any]]:
        today = date.today()
        env = load_env()
        checks = [
            {
                "key": "aster_sales",
                "label": "Aster ERP - vendas por item",
                "required_for_daily": True,
                "database": "core",
                "sql": "select max(refreshed_at) from public.dashboard_sales_fact",
            },
            {
                "key": "sales_cache",
                "label": "Cache comercial do dashboard",
                "required_for_daily": True,
                "database": "core",
                "sql": "select max(refreshed_at) from public.dashboard_sales_summary_cache",
            },
            {
                "key": "kommo",
                "label": "Kommo API - atendimento",
                "required_for_daily": True,
                "database": "crm",
                "sql": "select max(finished_at) from public.atendimento_ingestion_runs where status = 'sucesso'",
            },
            {
                "key": "drive_spreadsheets",
                "label": "Google Drive Archive - planilhas",
                "required_for_daily": True,
                "database": "core",
                "sql": "select ultima_sincronizacao from public.fontes_dados where nome = 'Google Drive Archive'",
            },
            {
                "key": "market_api",
                "label": "Mercado API - BCB e IBGE",
                "required_for_daily": False,
                "database": "core",
                "sql": "select max(finalizado_em) from public.mercado_coletas where status = 'sucesso' and source_key in ('bcb_dolar_ptax', 'ibge_pim_sidra', 'ibge_construcao_sidra')",
            },
            {
                "key": "market_aneel",
                "label": "Mercado ANEEL - geracao fotovoltaica",
                "required_for_daily": False,
                "database": "core",
                "sql": "select max(finalizado_em) from public.mercado_coletas where status = 'sucesso' and source_key = 'aneel_dados_abertos'",
            },
            {
                "key": "market_comex",
                "label": "Mercado Comex - importacoes por NCM aprovado",
                "required_for_daily": False,
                "database": "core",
                "sql": "select max(finalizado_em) from public.mercado_coletas where status = 'sucesso' and source_key = 'comex_stat_ncm'",
            },
            {
                "key": "market_world_bank",
                "label": "Mercado World Bank - contexto macro",
                "required_for_daily": False,
                "database": "core",
                "sql": "select max(finalizado_em) from public.mercado_coletas where status = 'sucesso' and source_key = 'world_bank_wdi'",
            },
            {
                "key": "market_obrasgov",
                "label": "Mercado ObrasGov - projetos publicos",
                "required_for_daily": False,
                "database": "core",
                "sql": "select max(finalizado_em) from public.mercado_coletas where status = 'sucesso' and source_key = 'obrasgov_projetos'",
            },
            {
                "key": "market_gov",
                "label": "Mercado governo - CAGED e PNCP",
                "required_for_daily": False,
                "database": "core",
                "sql": "select max(finalizado_em) from public.mercado_coletas where status = 'sucesso' and source_key in ('caged_microdados', 'pncp_consulta')",
            },
            {
                "key": "market_public",
                "label": "Mercado publico - Aco Brasil, CNI e INDA",
                "required_for_daily": False,
                "database": "core",
                "sql": "select max(finalizado_em) from public.mercado_coletas where status = 'sucesso'",
            },
        ]
        try:
            rows = []
            grouped = {
                "core": [item for item in checks if item["database"] == "core"],
                "crm": [item for item in checks if item["database"] == "crm"],
            }
            for database, items in grouped.items():
                connector = connect_crm_database if database == "crm" else connect_database
                with connector(env) as conn:
                    with conn.cursor() as cur:
                        for item in items:
                            cur.execute(item["sql"])
                            value = cur.fetchone()[0]
                            value_date = value.date() if value else None
                            rows.append(
                                {
                                    "key": item["key"],
                                    "label": item["label"],
                                    "required_for_daily": item["required_for_daily"],
                                    "last_success_at": value.isoformat() if value else None,
                                    "days_without_update": (today - value_date).days if value_date else None,
                                    "updated_today": value_date == today,
                                }
                            )
            return rows
        except Exception as exc:
            return [
                {
                    "key": "freshness_check",
                    "label": "Verificacao de atualizacao",
                    "required_for_daily": True,
                    "last_success_at": None,
                    "days_without_update": None,
                    "updated_today": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            ]

    async def _get_job(self, job_id: str) -> DashboardRefreshJob | None:
        async with self._lock:
            if self._current_job and self._current_job.job_id == job_id:
                return self._current_job
            for job in self._history:
                if job.job_id == job_id:
                    return job
        return None

    async def _update_job(self, job_id: str, **updates: Any) -> None:
        job: DashboardRefreshJob | None = None
        async with self._lock:
            job = self._current_job if self._current_job and self._current_job.job_id == job_id else None
            if not job:
                return
            for key, value in updates.items():
                setattr(job, key, value)
        await asyncio.to_thread(self._persist_job, job)

    async def _update_step(self, job_id: str, index: int, **updates: Any) -> None:
        step: RefreshStep | None = None
        async with self._lock:
            job = self._current_job if self._current_job and self._current_job.job_id == job_id else None
            if not job or index >= len(job.steps):
                return
            step = job.steps[index]
            for key, value in updates.items():
                setattr(step, key, value)
        if step:
            await asyncio.to_thread(self._persist_step, job_id, index, step)

    def serialize_job(self, job: DashboardRefreshJob | None) -> dict[str, Any] | None:
        return self._serialize_job(job)

    @staticmethod
    def _serialize_job(job: DashboardRefreshJob | None) -> dict[str, Any] | None:
        if job is None:
            return None
        return {
            "job_id": job.job_id,
            "mode": job.mode,
            "status": job.status,
            "date_from": job.date_from,
            "date_to": job.date_to,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "message": job.message,
            "steps": [
                {
                    "key": step.key,
                    "label": step.label,
                    "status": step.status,
                    "started_at": step.started_at,
                    "finished_at": step.finished_at,
                    "return_code": step.return_code,
                    "error": step.error,
                }
                for step in job.steps
            ],
        }

    @staticmethod
    def _job_from_payload(payload: dict[str, Any]) -> DashboardRefreshJob:
        return DashboardRefreshJob(
            job_id=payload["job_id"],
            mode=payload["mode"],
            status=payload["status"],
            date_from=payload["date_from"],
            date_to=payload["date_to"],
            created_at=payload["created_at"],
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            message=payload.get("message") or "",
            steps=[
                RefreshStep(
                    key=step["key"],
                    label=step["label"],
                    status=step["status"],
                    started_at=step.get("started_at"),
                    finished_at=step.get("finished_at"),
                    return_code=step.get("return_code"),
                    error=step.get("error"),
                )
                for step in payload.get("steps", [])
            ],
        )

    @staticmethod
    def _parse_last_json(stdout: str) -> dict[str, Any] | None:
        text = stdout.strip()
        if not text:
            return None
        start = text.rfind("\n{")
        if start >= 0:
            text = text[start + 1 :]
        elif not text.startswith("{"):
            start = text.find("{")
            if start >= 0:
                text = text[start:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _persist_job(self, job: DashboardRefreshJob) -> None:
        env = load_env()
        try:
            with connect_database(env) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into public.dashboard_refresh_runs(
                          job_id, mode, status, date_from, date_to, message,
                          created_at, started_at, finished_at, updated_at
                        )
                        values (%s::uuid, %s, %s, %s::date, %s::date, %s, %s::timestamptz, %s::timestamptz, %s::timestamptz, now())
                        on conflict (job_id)
                        do update set
                          mode = excluded.mode,
                          status = excluded.status,
                          date_from = excluded.date_from,
                          date_to = excluded.date_to,
                          message = excluded.message,
                          started_at = excluded.started_at,
                          finished_at = excluded.finished_at,
                          updated_at = now()
                        """,
                        (
                            job.job_id,
                            job.mode,
                            job.status,
                            job.date_from,
                            job.date_to,
                            job.message,
                            job.created_at,
                            job.started_at,
                            job.finished_at,
                        ),
                    )
                    for index, step in enumerate(job.steps):
                        self._persist_step_with_cursor(cur, job.job_id, index, step)
                    conn.commit()
        except Exception:
            return

    def _persist_step(self, job_id: str, index: int, step: RefreshStep) -> None:
        env = load_env()
        try:
            with connect_database(env) as conn:
                with conn.cursor() as cur:
                    self._persist_step_with_cursor(cur, job_id, index, step)
                    conn.commit()
        except Exception:
            return

    @staticmethod
    def _persist_step_with_cursor(cur: Any, job_id: str, index: int, step: RefreshStep) -> None:
        cur.execute(
            """
            insert into public.dashboard_refresh_steps(
              job_id, step_index, step_key, label, status, started_at, finished_at,
              return_code, stdout_tail, stderr_tail, result, error, updated_at
            )
            values (%s::uuid, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s, %s, %s, %s::jsonb, %s, now())
            on conflict (job_id, step_index)
            do update set
              step_key = excluded.step_key,
              label = excluded.label,
              status = excluded.status,
              started_at = excluded.started_at,
              finished_at = excluded.finished_at,
              return_code = excluded.return_code,
              stdout_tail = excluded.stdout_tail,
              stderr_tail = excluded.stderr_tail,
              result = excluded.result,
              error = excluded.error,
              updated_at = now()
            """,
            (
                job_id,
                index,
                step.key,
                step.label,
                step.status,
                step.started_at,
                step.finished_at,
                step.return_code,
                step.stdout_tail,
                step.stderr_tail,
                json.dumps(step.result, ensure_ascii=False) if step.result is not None else None,
                step.error,
            ),
        )

    def _stored_jobs(self) -> dict[str, Any]:
        env = load_env()
        try:
            self._mark_stale_jobs()
            with connect_database(env) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        select job_id::text, mode, status, date_from::text, date_to::text,
                               created_at, started_at, finished_at, message
                        from public.dashboard_refresh_runs
                        order by created_at desc
                        limit 5
                        """
                    )
                    run_rows = cur.fetchall()
                    if not run_rows:
                        return {"current": None, "history": []}
                    job_ids = [row[0] for row in run_rows]
                    cur.execute(
                        """
                        select job_id::text, step_index, step_key, label, status, started_at, finished_at,
                               return_code, error
                        from public.dashboard_refresh_steps
                        where job_id::text = any(%s)
                        order by job_id, step_index
                        """,
                        (job_ids,),
                    )
                    steps_by_job: dict[str, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
                    for row in cur.fetchall():
                        steps_by_job.setdefault(row[0], []).append(
                            {
                                "key": row[2],
                                "label": row[3],
                                "status": row[4],
                                "started_at": row[5].isoformat() if row[5] else None,
                                "finished_at": row[6].isoformat() if row[6] else None,
                                "return_code": row[7],
                                "error": row[8],
                            }
                        )
                    jobs = [
                        {
                            "job_id": row[0],
                            "mode": row[1],
                            "status": row[2],
                            "date_from": row[3],
                            "date_to": row[4],
                            "created_at": row[5].isoformat() if row[5] else None,
                            "started_at": row[6].isoformat() if row[6] else None,
                            "finished_at": row[7].isoformat() if row[7] else None,
                            "message": row[8],
                            "steps": steps_by_job.get(row[0], []),
                        }
                        for row in run_rows
                    ]
                    current = next((job for job in jobs if job["status"] in {"queued", "running"}), None)
                    return {"current": current, "history": jobs}
        except Exception:
            return {"current": None, "history": []}

    def _mark_stale_jobs(self) -> None:
        env = load_env()
        try:
            with connect_database(env) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update public.dashboard_refresh_steps s
                        set status = case when s.status = 'running' then 'failed' else 'skipped' end,
                            finished_at = coalesce(s.finished_at, now()),
                            error = coalesce(s.error, 'Job interrompido antes de concluir. O processo web pode ter reiniciado ou excedido recursos.'),
                            updated_at = now()
                        from public.dashboard_refresh_runs r
                        where s.job_id = r.job_id
                          and r.status in ('queued', 'running')
                          and r.updated_at < now() - (%s || ' minutes')::interval
                          and s.status in ('queued', 'running')
                        """,
                        (STALE_REFRESH_MINUTES,),
                    )
                    cur.execute(
                        """
                        update public.dashboard_refresh_runs
                        set status = 'failed',
                            finished_at = coalesce(finished_at, now()),
                            message = 'Atualizacao interrompida antes de concluir. Inicie uma nova atualizacao.',
                            updated_at = now()
                        where status in ('queued', 'running')
                          and updated_at < now() - (%s || ' minutes')::interval
                        """,
                        (STALE_REFRESH_MINUTES,),
                    )
                    conn.commit()
        except Exception:
            return


dashboard_refresh_manager = DashboardRefreshManager()
