from __future__ import annotations

from typing import Dict

from sqlalchemy.orm import Session

from app.config import settings
from app.notifications import NotificationService
from app.repositories import JobRepository
from app.scrapers.discovery import SourceDiscoveryService
from app.settings_manager import get_profile


class JobPipeline:
    def __init__(self) -> None:
        self.repository = JobRepository()
        self.notifier = NotificationService()

    def _infer_company_type(self, company: str) -> str:
        name = (company or "").lower()
        if any(token in name for token in ["labs", "ai", "tech", "cloud", "data"]):
            return "product"
        if any(token in name for token in ["consult", "services", "solutions"]):
            return "service"
        return "unknown"

    def _normalize_job(self, raw: dict) -> dict:
        company = raw.get("company") or "Unknown"
        normalized = {**raw}
        normalized["title"] = (raw.get("title") or "").strip()[:300]
        normalized["company"] = company.strip()[:255]
        normalized["location"] = (raw.get("location") or "Unknown").strip()[:255]
        normalized["description"] = (raw.get("description") or "").strip()
        normalized["company_type"] = raw.get("company_type") or self._infer_company_type(company)
        normalized["skills"] = raw.get("skills") or []
        return normalized

    async def run(self, db: Session) -> Dict:
        run = self.repository.create_run(db)
        profile = get_profile(db)
        roles = profile.get("roles") or settings.role_list
        locations = profile.get("locations") or settings.location_list
        preferred_skills = profile.get("skills") or []
        excluded_companies = [item.lower() for item in (profile.get("excluded_companies") or [])]
        discovery = SourceDiscoveryService(settings.load_source_catalog())

        try:
            fetched_jobs = await discovery.fetch_all(roles=roles, locations=locations)
            normalized = [self._normalize_job(item) for item in fetched_jobs if item.get("url") and item.get("title")]
            inserted, qualified, super_jobs, alert_jobs = self.repository.save_jobs(
                db,
                normalized,
                excluded_companies,
                preferred_skills=preferred_skills,
            )
            self.repository.finalize_run(
                db,
                run,
                fetched=len(normalized),
                inserted=inserted,
                qualified=qualified,
            )
            await self.notifier.notify_discord_run(
                alert_jobs,
                run_summary={
                    "run_id": run.id,
                    "fetched": len(normalized),
                    "inserted": inserted,
                    "qualified": qualified,
                    "super_priority": len(super_jobs),
                },
            )
            await self.notifier.notify_all_jobs(
                alert_jobs,
                run_summary={
                    "run_id": run.id,
                    "fetched": len(normalized),
                    "inserted": inserted,
                    "qualified": qualified,
                    "super_priority": len(super_jobs),
                },
            )
            await self.notifier.notify_super_priority(super_jobs)
            return {
                "run_id": run.id,
                "fetched": len(normalized),
                "inserted": inserted,
                "qualified": qualified,
                "super_priority": len(super_jobs),
            }
        except Exception as exc:
            self.repository.finalize_run(db, run, fetched=0, inserted=0, qualified=0, error=str(exc))
            await self.notifier.notify_discord_run(
                [],
                run_summary={
                    "run_id": run.id,
                    "fetched": 0,
                    "inserted": 0,
                    "qualified": 0,
                    "super_priority": 0,
                    "error": str(exc),
                },
            )
            return {
                "run_id": run.id,
                "fetched": 0,
                "inserted": 0,
                "qualified": 0,
                "super_priority": 0,
                "error": str(exc),
            }
