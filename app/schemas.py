from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    job_id: str
    title: str
    company: str
    location: str
    url: str
    source: str
    posted_time: datetime | None
    interview_probability: float
    salary_fit_probability: float
    stack_match: float
    is_super_priority: bool
    is_ultra_low_competition: bool
    apply_within_6_hours: bool

    class Config:
        from_attributes = True


class SettingsPayload(BaseModel):
    roles: List[str]
    locations: List[str]
    skills: List[str]
    experience_min: int
    experience_max: int
    salary_min_lpa: int
    salary_max_lpa: int
    auto_run_enabled: bool
    scan_times: List[str]
    scan_interval_hours: int
    excluded_companies: List[str]


class AnalyticsOut(BaseModel):
    total_jobs: int
    qualified_jobs: int
    average_interview_probability: float
    average_salary_fit: float
    super_priority_count: int
    top_three_titles: List[str]
    posting_heatmap: dict


class ScanRequestOut(BaseModel):
    id: str
    status: str
    trigger_source: str
    requested_by: str
    requested_by_id: str
    request_channel_id: str
    request_guild_id: str
    requested_at: datetime
    claimed_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    worker_id: str
    attempt_count: int
    error_message: str
    request_metadata: dict
    result_payload: dict
