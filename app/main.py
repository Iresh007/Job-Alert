from __future__ import annotations

import asyncio
import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_session, init_db
from app.logging_utils import log_event
from app.pipeline import JobPipeline
from app.repositories import JobRepository
from app.scan_queue import ScanQueueService
from app.schemas import AnalyticsOut, JobOut, ScanRequestOut, SettingsPayload
from app.scheduler import build_scheduler
from app.settings_manager import get_profile, update_profile


app = FastAPI(title="Autonomous Job Search Intelligence Platform", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
repository = JobRepository()
pipeline = JobPipeline()
scan_queue = ScanQueueService()
_scheduler = None
_profile_watch_task = None
_scheduler_profile_signature = ""


def _dashboard_root() -> Path:
    return Path(__file__).resolve().parents[1] / "dashboard"


def _build_scheduled_enqueue():
    async def scheduled_enqueue() -> None:
        db = SessionLocal()
        try:
            request, created = scan_queue.enqueue(
                db,
                trigger_source="scheduler",
                requested_by="scheduler",
                requested_by_id="scheduler",
                request_metadata={"source": "scheduler"},
            )
            log_event(
                "scheduled_scan_enqueued",
                request_id=request.id,
                created=created,
                status=request.status,
            )
        finally:
            db.close()

    return scheduled_enqueue


async def _run_pipeline_with_new_session() -> dict:
    db = SessionLocal()
    try:
        return await pipeline.run(db)
    finally:
        db.close()


def _read_profile_with_new_session() -> dict:
    db = SessionLocal()
    try:
        return get_profile(db)
    finally:
        db.close()


def _write_profile_with_new_session(payload: dict) -> dict:
    db = SessionLocal()
    try:
        updated = update_profile(db, payload)
    finally:
        db.close()
    _restart_scheduler(profile=updated)
    return updated


def _enqueue_scan_request_with_new_session(
    *,
    trigger_source: str,
    requested_by: str = "",
    requested_by_id: str = "",
    request_channel_id: str = "",
    request_guild_id: str = "",
    request_metadata: dict | None = None,
) -> dict:
    db = SessionLocal()
    try:
        request, created = scan_queue.enqueue(
            db,
            trigger_source=trigger_source,
            requested_by=requested_by,
            requested_by_id=requested_by_id,
            request_channel_id=request_channel_id,
            request_guild_id=request_guild_id,
            request_metadata=request_metadata,
        )
        payload = scan_queue.to_dict(request)
        payload["created"] = created
        return payload
    finally:
        db.close()


def _restart_scheduler(profile: dict | None = None) -> None:
    global _scheduler, _scheduler_profile_signature
    if _scheduler:
        _scheduler.shutdown(wait=False)
    effective_profile = profile or {}
    _scheduler = build_scheduler(_build_scheduled_enqueue(), profile=effective_profile)
    _scheduler.start()
    _scheduler_profile_signature = json.dumps(effective_profile, sort_keys=True)


async def _watch_profile_updates() -> None:
    global _scheduler_profile_signature
    while True:
        await asyncio.sleep(10)
        db = SessionLocal()
        try:
            profile = get_profile(db)
        finally:
            db.close()
        signature = json.dumps(profile, sort_keys=True)
        if signature != _scheduler_profile_signature:
            _restart_scheduler(profile=profile)
            log_event("scheduler_reloaded_from_profile_change")


@app.on_event("startup")
async def startup() -> None:
    global _profile_watch_task
    init_db()
    db = SessionLocal()
    try:
        profile = get_profile(db)
    finally:
        db.close()
    _restart_scheduler(profile=profile)
    _profile_watch_task = asyncio.create_task(_watch_profile_updates())


@app.on_event("shutdown")
async def shutdown() -> None:
    global _profile_watch_task
    if _scheduler:
        _scheduler.shutdown(wait=False)
    if _profile_watch_task:
        _profile_watch_task.cancel()
        _profile_watch_task = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


def _require_admin_token(x_admin_token: str | None = None) -> None:
    configured = (settings.admin_api_token or "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="ADMIN_API_TOKEN is not configured.")
    if x_admin_token != configured:
        raise HTTPException(status_code=403, detail="Invalid admin token.")


@app.post("/api/scan/run", response_model=ScanRequestOut)
def run_scan() -> dict:
    request = _enqueue_scan_request_with_new_session(
        trigger_source="api",
        requested_by="api",
        requested_by_id="api",
        request_metadata={"source": "public_api"},
    )
    request.pop("created", None)
    return request


@app.get("/api/scan/requests/{request_id}", response_model=ScanRequestOut)
def read_scan_request(request_id: str, db: Session = Depends(get_session)) -> dict:
    request = scan_queue.get_request(db, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Scan request not found.")
    return scan_queue.to_dict(request)


@app.post("/api/admin/scan/run", response_model=ScanRequestOut)
def admin_run_scan(x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin_token(x_admin_token)
    request = _enqueue_scan_request_with_new_session(
        trigger_source="admin_api",
        requested_by="admin_api",
        requested_by_id="admin_api",
        request_metadata={"source": "admin_api"},
    )
    request.pop("created", None)
    return request


@app.get("/api/admin/scan/requests/{request_id}", response_model=ScanRequestOut)
def admin_read_scan_request(request_id: str, x_admin_token: str | None = Header(default=None), db: Session = Depends(get_session)) -> dict:
    _require_admin_token(x_admin_token)
    request = scan_queue.get_request(db, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Scan request not found.")
    return scan_queue.to_dict(request)


@app.get("/api/jobs", response_model=List[JobOut])
def list_jobs(
    min_score: float = Query(default=70, ge=0, le=100),
    super_only: bool = False,
    limit: int = Query(default=300, ge=1, le=1000),
    db: Session = Depends(get_session),
):
    return repository.list_jobs(db, min_score=min_score, limit=limit, super_only=super_only)


def _jobs_to_excel_xml(jobs: list) -> str:
    rows = [
        [
            "Job ID",
            "Title",
            "Company",
            "Location",
            "URL",
            "Source",
            "Posted Time",
            "Interview Probability",
            "Salary Fit",
            "Stack Match",
            "Super Priority",
            "Ultra Low Competition",
            "Apply Within 6 Hours",
        ]
    ]

    for job in jobs:
        rows.append(
            [
                job.job_id or "",
                job.title or "",
                job.company or "",
                job.location or "",
                job.url or "",
                job.source or "",
                job.posted_time.isoformat() if job.posted_time else "",
                f"{job.interview_probability:.2f}",
                f"{job.salary_fit_probability:.2f}",
                f"{job.stack_match:.2f}",
                "Yes" if job.is_super_priority else "No",
                "Yes" if job.is_ultra_low_competition else "No",
                "Yes" if job.apply_within_6_hours else "No",
            ]
        )

    xml_rows = []
    for row in rows:
        cells = "".join(
            f'<Cell><Data ss:Type="String">{escape(str(cell))}</Data></Cell>'
            for cell in row
        )
        xml_rows.append(f"<Row>{cells}</Row>")

    xml_content = f"""<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Jobs">
  <Table>
   {''.join(xml_rows)}
  </Table>
 </Worksheet>
</Workbook>
"""
    return xml_content


@app.get("/api/jobs/export/excel")
def export_jobs_excel(
    min_score: float = Query(default=70, ge=0, le=100),
    super_only: bool = False,
    limit: int = Query(default=2000, ge=1, le=10000),
    db: Session = Depends(get_session),
):
    jobs = repository.list_jobs(db, min_score=min_score, limit=limit, super_only=super_only)
    xml_payload = _jobs_to_excel_xml(jobs)
    filename = f"job_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xls"
    return Response(
        content=xml_payload,
        media_type="application/vnd.ms-excel",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs/top3", response_model=List[JobOut])
def top_three(db: Session = Depends(get_session)):
    return repository.top_three(db)


@app.get("/api/analytics", response_model=AnalyticsOut)
def analytics(db: Session = Depends(get_session)):
    return repository.analytics(db)


@app.get("/api/runs")
def runs(db: Session = Depends(get_session)):
    rows = repository.list_runs(db)
    return [
        {
            "id": row.id,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "total_fetched": row.total_fetched,
            "total_inserted": row.total_inserted,
            "total_qualified": row.total_qualified,
            "status": row.status,
            "error_message": row.error_message,
        }
        for row in rows
    ]


@app.get("/api/scheduler/next-runs")
def next_runs(limit: int = Query(default=10, ge=1, le=50)):
    if not _scheduler:
        return []
    jobs = [job for job in _scheduler.get_jobs() if job.next_run_time]
    jobs.sort(key=lambda job: job.next_run_time or datetime.max)
    return [
        {
            "job_id": job.id,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in jobs[:limit]
    ]


@app.get("/api/settings")
def read_settings(db: Session = Depends(get_session)):
    return get_profile(db)


@app.put("/api/settings")
async def write_settings(payload: SettingsPayload, db: Session = Depends(get_session)):
    updated = update_profile(db, payload.model_dump())
    _restart_scheduler(profile=updated)
    return updated


app.mount("/dashboard", StaticFiles(directory=_dashboard_root()), name="dashboard")


@app.get("/")
def dashboard_home() -> FileResponse:
    return FileResponse(_dashboard_root() / "index.html")
