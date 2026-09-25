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
    deliverables: list[str] = Field(default_factory=list)
    notes: str


class DataRequirementInfo(BaseModel):
    key: str
    title: str
    priority: str
    refresh: str
    grain: str
    objective: str
    fields: list[str]
    known_sources: list[str]
    gaps: list[str]


class ExternalSpreadsheetSourceInfo(BaseModel):
    key: str
    title: str
    folder_url: str
    selection_rule: str
    latest_file_id: str
    latest_file_name: str
    latest_modified_time: str
    local_path: str
    likely_coverage: list[str]
    notes: str


class DataRequirementsResponse(BaseModel):
    requirements: list[DataRequirementInfo]
    external_spreadsheet_sources: list[ExternalSpreadsheetSourceInfo] = Field(default_factory=list)
    extraction_rules: list[str]


class LocalSpreadsheetInspectionRequest(BaseModel):
    input_dir: str = Field(default="Planilhas", description="Workspace-relative directory containing .xlsx files.")


class LocalSpreadsheetInspectionResponse(BaseModel):
    files: int
    input_dir: str
    output_json: str
    output_md: str
    warning: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class IntelligenceDomainInfo(BaseModel):
    key: str
    title: str
    description: str
    status: str
    sources: list[str]
    current_scope: list[str]
    next_scope: list[str]
    boundaries: list[str]


class IntelligenceDomainsResponse(BaseModel):
    domains: list[IntelligenceDomainInfo]


class SalesRegionRow(BaseModel):
    canal: str
    regiao: str
    linhas: int
    valor_total: str
    criterios: dict[str, int]
