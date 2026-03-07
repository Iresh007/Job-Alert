from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import UserSetting


DEFAULT_KEY = "search_profile"


def default_profile() -> Dict[str, Any]:
    return {
        "roles": settings.role_list,
        "locations": settings.location_list,
        "experience_min": settings.default_experience_min,
        "experience_max": settings.default_experience_max,
        "salary_min_lpa": settings.default_salary_min_lpa,
        "salary_max_lpa": settings.default_salary_max_lpa,
        "scan_interval_hours": settings.scan_interval_hours,
        "auto_run_enabled": True,
        "scan_times": ["08:00", "12:00", "16:00", "23:00"],
        "skills": [
            "Azure Databricks",
            "Snowflake",
            "Azure Data Factory",
            "ADLS Gen2",
            "PySpark",
            "SQL",
            "Data Vault 2.0",
            "Medallion Architecture",
            "Jenkins",
            "Azure DevOps",
            "GitHub",
        ],
        "excluded_companies": settings.excluded_company_list,
    }


def _merge_with_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    merged = default_profile()
    merged.update(payload or {})
    if not isinstance(merged.get("scan_times"), list):
        merged["scan_times"] = ["08:00", "12:00", "16:00", "23:00"]
    if not isinstance(merged.get("skills"), list):
        merged["skills"] = default_profile()["skills"]
    return merged


def get_profile(db: Session) -> Dict[str, Any]:
    record = db.scalar(select(UserSetting).where(UserSetting.key == DEFAULT_KEY))
    if not record:
        profile = default_profile()
        db.add(UserSetting(key=DEFAULT_KEY, value=profile))
        db.commit()
        return profile
    merged = _merge_with_defaults(record.value)
    if merged != record.value:
        record.value = merged
        db.commit()
    return merged


def update_profile(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    merged_payload = _merge_with_defaults(payload)
    record = db.scalar(select(UserSetting).where(UserSetting.key == DEFAULT_KEY))
    if not record:
        record = UserSetting(key=DEFAULT_KEY, value=merged_payload)
        db.add(record)
    else:
        record.value = merged_payload
    db.commit()
    db.refresh(record)
    return record.value
