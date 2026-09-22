from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.api.models import JobRecord


ROOT = Path(__file__).resolve().parents[2]


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create_aster_extraction(
        self,
        *,
        query_id: str,
        date_from: str | None,
        date_to: str | None,
        timeout_seconds: int,
    ) -> JobRecord:
        job_id = str(uuid.uuid4())
        command = [
            sys.executable,
            str(ROOT / "tools" / "aster_live_execute_ingest.py"),
            "--query-id",
            query_id,
            "--timeout-seconds",
            str(timeout_seconds),
        ]
        if date_from:
            command.extend(["--date-from", date_from])
        if date_to:
            command.extend(["--date-to", date_to])

        record = JobRecord(
            job_id=job_id,
            status="queued",
            query_id=query_id,
            command=command,
            created_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._jobs[job_id] = record
        asyncio.create_task(self._run_job(job_id))
        return record

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_recent(self) -> list[JobRecord]:
        async with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)[:50]

    async def _run_job(self, job_id: str) -> None:
        record = await self.get(job_id)
        if record is None:
            return

        await self._update(job_id, status="running", started_at=datetime.now(timezone.utc))
        try:
            process = await asyncio.create_subprocess_exec(
                *record.command,
                cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await process.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            result = self._parse_last_json(stdout)
            status = "succeeded" if process.returncode == 0 else "failed"
            await self._update(
                job_id,
                status=status,
                finished_at=datetime.now(timezone.utc),
                return_code=process.returncode,
                stdout=stdout[-8000:],
                stderr=stderr[-8000:],
                result=result,
                error=None if status == "succeeded" else (stderr or stdout)[-2000:],
            )
        except Exception as exc:
            await self._update(
                job_id,
                status="failed",
                finished_at=datetime.now(timezone.utc),
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _update(self, job_id: str, **updates: object) -> None:
        async with self._lock:
            current = self._jobs[job_id]
            self._jobs[job_id] = current.model_copy(update=updates)

    @staticmethod
    def _parse_last_json(stdout: str) -> dict | None:
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


job_manager = JobManager()
