from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.config import get_api_settings
from backend.api.data import (
    internal_dashboard_summary,
    list_domains,
    list_reports,
    list_requirements,
    sales_regions_summary,
)
from backend.api.jobs import job_manager
from backend.api.models import (
    DataRequirementsResponse,
    ExtractionRequest,
    ExtractionResponse,
    IntelligenceDomainsResponse,
    JobRecord,
    LocalSpreadsheetInspectionRequest,
    LocalSpreadsheetInspectionResponse,
    ReportInfo,
    SalesRegionRow,
)
from backend.api.security import require_api_key, require_dashboard_read_key, set_dashboard_session_cookie
from backend.api.update_orchestrator import dashboard_refresh_manager
from backend.aster_collector.local_spreadsheets import inspect_local_spreadsheet_sources


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"

settings = get_api_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API para disparar extrações autorizadas do Aster e consultar dados classificados do ABR Intelligence.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "abr-data-api"}


@app.on_event("startup")
async def start_dashboard_auto_refresh() -> None:
    asyncio.create_task(dashboard_refresh_manager.run_auto_refresh_loop())


@app.get("/v1/aster/reports", response_model=list[ReportInfo], tags=["aster"], dependencies=[Depends(require_api_key)])
async def get_aster_reports() -> list[dict]:
    return list_reports()


@app.get(
    "/v1/aster/requirements",
    response_model=DataRequirementsResponse,
    tags=["aster"],
    dependencies=[Depends(require_api_key)],
)
async def get_aster_requirements() -> dict:
    return list_requirements()


@app.get(
    "/v1/intelligence/domains",
    response_model=IntelligenceDomainsResponse,
    tags=["intelligence"],
    dependencies=[Depends(require_api_key)],
)
async def get_intelligence_domains() -> dict:
    return list_domains()


@app.get(
    "/v1/dashboard/internal",
    response_model=dict,
    tags=["dashboard"],
)
async def get_internal_dashboard(
    response: Response,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    market_tab: str | None = Query(default=None),
    market_date_from: date | None = Query(default=None),
    market_date_to: date | None = Query(default=None),
    include_sales_regions: bool = Query(default=False),
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before or equal to date_to.")
    if market_date_from and market_date_to and market_date_from > market_date_to:
        raise HTTPException(status_code=422, detail="market_date_from must be before or equal to market_date_to.")
    set_dashboard_session_cookie(response)
    asyncio.create_task(dashboard_refresh_manager.ensure_daily_refresh(date_from=None, date_to=None))
    return await asyncio.to_thread(
        internal_dashboard_summary,
        date_from=date_from,
        date_to=date_to,
        include_sales_regions=include_sales_regions,
        market_tab=market_tab,
        market_date_from=market_date_from,
        market_date_to=market_date_to,
    )


@app.post(
    "/v1/dashboard/refresh",
    response_model=dict,
    tags=["dashboard"],
    dependencies=[Depends(require_dashboard_read_key)],
)
async def refresh_dashboard_data(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    force: bool = Query(default=True),
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be before or equal to date_to.")
    job = await dashboard_refresh_manager.start_refresh(
        mode="manual",
        date_from=date_from,
        date_to=date_to,
        force=force,
    )
    return {"job": dashboard_refresh_manager.serialize_job(job)}


@app.get(
    "/v1/dashboard/refresh",
    response_model=dict,
    tags=["dashboard"],
    dependencies=[Depends(require_dashboard_read_key)],
)
async def get_dashboard_refresh_status() -> dict:
    return await dashboard_refresh_manager.status()


@app.post(
    "/v1/spreadsheets/local/inspect",
    response_model=LocalSpreadsheetInspectionResponse,
    tags=["spreadsheets"],
    dependencies=[Depends(require_api_key)],
)
async def inspect_local_spreadsheets(request: LocalSpreadsheetInspectionRequest) -> dict:
    return inspect_local_spreadsheet_sources(input_dir=request.input_dir)


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


if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str) -> FileResponse:
    if full_path.startswith(("v1/", "health", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not found.")

    index_path = FRONTEND_DIST / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found.")
    return FileResponse(index_path)
