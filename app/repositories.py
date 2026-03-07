from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.dedupe import DedupeEngine, title_fingerprint, url_hash
from app.models import Job, RunHistory
from app.scoring import ScoringEngine


class JobRepository:
    def __init__(self) -> None:
        self.dedupe = DedupeEngine()
        self.scoring = ScoringEngine()

    def create_run(self, db: Session) -> RunHistory:
        run = RunHistory(status="running")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def finalize_run(self, db: Session, run: RunHistory, fetched: int, inserted: int, qualified: int, error: str = "") -> RunHistory:
        run.total_fetched = fetched
        run.total_inserted = inserted
        run.total_qualified = qualified
        run.finished_at = datetime.now(timezone.utc)
        run.status = "failed" if error else "completed"
        run.error_message = error
        db.commit()
        db.refresh(run)
        return run

    def _skill_match(self, job: dict, preferred_skills: List[str]) -> bool:
        if not preferred_skills:
            return True
        combined_text = " ".join(
            [
                job.get("title", ""),
                job.get("description", ""),
                " ".join(job.get("skills", []) or []),
            ]
        ).lower()
        if any(skill.lower() in combined_text for skill in preferred_skills):
            return True
        # Keep explicit target roles even if skill keywords are missing in text.
        title = (job.get("title") or "").lower()
        return any(term in title for term in ["data engineer", "databricks", "azure data", "snowflake"])

    def save_jobs(
        self,
        db: Session,
        raw_jobs: List[dict],
        excluded_companies: List[str],
        preferred_skills: List[str] | None = None,
    ) -> tuple[int, int, list]:
        inserted = 0
        qualified = 0
        super_priority_jobs: list = []
        preferred_skills = preferred_skills or []

        for raw in raw_jobs:
            company_name = (raw.get("company") or "").strip()
            if company_name.lower() in excluded_companies:
                continue
            if not self._skill_match(raw, preferred_skills):
                continue
            if self.dedupe.is_duplicate(db, raw):
                continue

            score = self.scoring.score(raw, preferred_skills=preferred_skills)
            if score.interview_probability < 70:
                continue

            model = Job(
                job_id=raw.get("job_id", ""),
                title=raw.get("title", ""),
                company=company_name or "Unknown",
                location=raw.get("location", "Unknown"),
                url=raw.get("url", ""),
                description=raw.get("description", ""),
                skills=raw.get("skills", []),
                posted_time=raw.get("posted_time"),
                experience_required=raw.get("experience_required", ""),
                company_type=raw.get("company_type", "unknown"),
                source=raw.get("source", "unknown"),
                recruiter_name=raw.get("recruiter_name", ""),
                interview_probability=score.interview_probability,
                salary_fit_probability=score.salary_fit_probability,
                stack_match=score.stack_match,
                is_super_priority=score.is_super_priority,
                is_ultra_low_competition=score.is_ultra_low_competition,
                apply_within_6_hours=score.apply_within_6_hours,
                url_hash=url_hash(raw.get("url", "")),
                title_fingerprint=title_fingerprint(raw.get("title", "")),
                net_new=True,
            )
            db.add(model)
            self.dedupe.persist_fingerprint(db, raw)
            inserted += 1
            qualified += 1
            if score.is_super_priority:
                super_priority_jobs.append(
                    {
                        "title": model.title,
                        "company": model.company,
                        "location": model.location,
                        "url": model.url,
                        "interview_probability": model.interview_probability,
                        "is_ultra_low_competition": model.is_ultra_low_competition,
                    }
                )

        db.commit()
        return inserted, qualified, super_priority_jobs

    def list_jobs(self, db: Session, min_score: float = 70, limit: int = 300, super_only: bool = False) -> List[Job]:
        query = select(Job).where(Job.interview_probability >= min_score)
        if super_only:
            query = query.where(Job.is_super_priority.is_(True))
        query = query.order_by(desc(Job.interview_probability), desc(Job.posted_time), desc(Job.created_at)).limit(limit)
        return db.scalars(query).all()

    def top_three(self, db: Session) -> List[Job]:
        query = select(Job).where(Job.interview_probability >= 70).order_by(desc(Job.interview_probability)).limit(3)
        return db.scalars(query).all()

    def analytics(self, db: Session) -> dict:
        total_jobs = db.scalar(select(func.count(Job.id))) or 0
        qualified_jobs = db.scalar(select(func.count(Job.id)).where(Job.interview_probability >= 70)) or 0
        avg_interview = db.scalar(select(func.avg(Job.interview_probability))) or 0.0
        avg_salary = db.scalar(select(func.avg(Job.salary_fit_probability))) or 0.0
        super_priority = db.scalar(select(func.count(Job.id)).where(Job.is_super_priority.is_(True))) or 0
        top_titles = [item.title for item in self.top_three(db)]

        heatmap_rows = db.execute(
            select(func.extract("hour", func.coalesce(Job.posted_time, Job.created_at)).label("hour"), func.count(Job.id)).group_by("hour")
        ).all()
        heatmap = {str(int(hour)): count for hour, count in heatmap_rows}
        for hour in range(24):
            heatmap.setdefault(str(hour), 0)

        return {
            "total_jobs": int(total_jobs),
            "qualified_jobs": int(qualified_jobs),
            "average_interview_probability": round(float(avg_interview), 2),
            "average_salary_fit": round(float(avg_salary), 2),
            "super_priority_count": int(super_priority),
            "top_three_titles": top_titles,
            "posting_heatmap": heatmap,
        }

    def list_runs(self, db: Session, limit: int = 30) -> List[RunHistory]:
        query = select(RunHistory).order_by(desc(RunHistory.started_at)).limit(limit)
        return db.scalars(query).all()
