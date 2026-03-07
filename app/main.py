from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_session, init_db
from app.pipeline import JobPipeline
from app.repositories import JobRepository
from app.schemas import AnalyticsOut, JobOut, SettingsPayload
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
_scheduler = None


def _dashboard_root() -> Path:
    return Path(__file__).resolve().parents[1] / "dashboard"


def _build_scheduled_run():
    async def scheduled_run() -> None:
        db = SessionLocal()
        try:
            await pipeline.run(db)
        finally:
            db.close()

    return scheduled_run


def _restart_scheduler(profile: dict | None = None) -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
    _scheduler = build_scheduler(_build_scheduled_run(), profile=profile)
    _scheduler.start()


@app.on_event("startup")
async def startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        profile = get_profile(db)
    finally:
        db.close()
    _restart_scheduler(profile=profile)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/scan/run")
async def run_scan(db: Session = Depends(get_session)) -> dict:
    return await pipeline.run(db)


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
