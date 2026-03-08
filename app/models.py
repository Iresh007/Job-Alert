from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    posted_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    experience_required: Mapped[str] = mapped_column(String(100), default="")
    company_type: Mapped[str] = mapped_column(String(100), default="unknown")
    source: Mapped[str] = mapped_column(String(100), index=True)
    recruiter_name: Mapped[str] = mapped_column(String(150), default="")

    interview_probability: Mapped[float] = mapped_column(Float, default=0)
    salary_fit_probability: Mapped[float] = mapped_column(Float, default=0)
    stack_match: Mapped[float] = mapped_column(Float, default=0)

    is_super_priority: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ultra_low_competition: Mapped[bool] = mapped_column(Boolean, default=False)
    apply_within_6_hours: Mapped[bool] = mapped_column(Boolean, default=False)

    url_hash: Mapped[str] = mapped_column(String(128), index=True)
    title_fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    net_new: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("url_hash", name="uq_jobs_url_hash"),)


class Fingerprint(Base):
    __tablename__ = "fingerprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title_fingerprint: Mapped[str] = mapped_column(String(255), index=True)
    company_normalized: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class RunHistory(Base):
    __tablename__ = "run_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_inserted: Mapped[int] = mapped_column(Integer, default=0)
    total_qualified: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="running")
    error_message: Mapped[str] = mapped_column(Text, default="")


class UserSetting(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ScanRequest(Base):
    __tablename__ = "scan_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trigger_source: Mapped[str] = mapped_column(String(50), index=True, default="manual")
    status: Mapped[str] = mapped_column(String(30), index=True, default="queued")
    requested_by: Mapped[str] = mapped_column(String(255), default="")
    requested_by_id: Mapped[str] = mapped_column(String(100), default="")
    request_channel_id: Mapped[str] = mapped_column(String(100), default="")
    request_guild_id: Mapped[str] = mapped_column(String(100), default="")
    worker_id: Mapped[str] = mapped_column(String(255), default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    request_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
