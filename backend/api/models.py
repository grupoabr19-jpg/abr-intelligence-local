from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class ExtractionRequest(BaseModel):
    query_id: str = Field(default="D0A4D301", description="Aster ReportQuery ID.")
    date_from: date | None = Field(default=None, description="Start date for date-based reports.")
    date_to: date | None = Field(default=None, description="End date for date-based reports.")
    timeout_seconds: int = Field(default=600, ge=30, le=3600)


class ExtractionResponse(BaseModel):
    job_id: str
    status: JobStatus
    query_id: str
    status_url: str


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus
    query_id: str
    command: list[str]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None


class ReportInfo(BaseModel):
    query_id: str
    area: str
    name: str
    entity: str
    automation_status: str
    notes: str


class SalesRegionRow(BaseModel):
    canal: str
    regiao: str
    linhas: int
    valor_total: str
    criterios: dict[str, int]
