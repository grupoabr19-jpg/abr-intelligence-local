from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from backend.api.config import get_api_settings
from backend.api.data import list_reports, sales_regions_summary
from backend.api.jobs import job_manager
from backend.api.models import ExtractionRequest, ExtractionResponse, JobRecord, ReportInfo, SalesRegionRow
from backend.api.security import require_api_key


settings = get_api_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API para disparar extrações autorizadas do Aster e consultar dados classificados do ABR Intelligence.",
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "abr-data-api"}


@app.get("/v1/aster/reports", response_model=list[ReportInfo], tags=["aster"], dependencies=[Depends(require_api_key)])
async def get_aster_reports() -> list[dict[str, str]]:
    return list_reports()


@app.post(
    "/v1/aster/extractions",
    response_model=ExtractionResponse,
    tags=["aster"],
    dependencies=[Depends(require_api_key)],
)
async def start_aster_extraction(request: ExtractionRequest) -> ExtractionResponse:
    record = await job_manager.create_aster_extraction(
        query_id=request.query_id.upper(),
        date_from=request.date_from.isoformat() if request.date_from else None,
        date_to=request.date_to.isoformat() if request.date_to else None,
        timeout_seconds=request.timeout_seconds,
    )
    return ExtractionResponse(
        job_id=record.job_id,
        status=record.status,
        query_id=record.query_id,
        status_url=f"/v1/jobs/{record.job_id}",
    )


@app.get("/v1/jobs", response_model=list[JobRecord], tags=["jobs"], dependencies=[Depends(require_api_key)])
async def list_jobs() -> list[JobRecord]:
    return await job_manager.list_recent()


@app.get("/v1/jobs/{job_id}", response_model=JobRecord, tags=["jobs"], dependencies=[Depends(require_api_key)])
async def get_job(job_id: str) -> JobRecord:
    record = await job_manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record


@app.get(
    "/v1/sales/regions-summary",
    response_model=list[SalesRegionRow],
    tags=["sales"],
    dependencies=[Depends(require_api_key)],
)
async def get_sales_regions_summary() -> list[dict]:
    return sales_regions_summary()
