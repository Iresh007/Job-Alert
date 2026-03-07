from __future__ import annotations

import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings


TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _parse_times(time_slots: list[str]) -> list[tuple[int, int]]:
    parsed: list[tuple[int, int]] = []
    for item in time_slots or []:
        match = TIME_PATTERN.match((item or "").strip())
        if not match:
            continue
        hour = int(match.group(1))
        minute = int(match.group(2))
        parsed.append((hour, minute))
    return sorted(set(parsed))


def build_scheduler(scan_coroutine, profile: dict | None = None):
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    profile = profile or {}
    auto_run_enabled = bool(profile.get("auto_run_enabled", True))
    if not auto_run_enabled:
        return scheduler

    interval_hours = int(profile.get("scan_interval_hours") or settings.scan_interval_hours)
    scheduler.add_job(
        scan_coroutine,
        "interval",
        hours=max(interval_hours, 1),
        id="autonomous-scan-interval",
        max_instances=1,
        replace_existing=True,
    )

    time_slots = _parse_times(profile.get("scan_times") or [])
    if time_slots:
        for idx, (hour, minute) in enumerate(time_slots):
            scheduler.add_job(
                scan_coroutine,
                "cron",
                hour=hour,
                minute=minute,
                id=f"autonomous-scan-{idx}",
                max_instances=1,
                replace_existing=True,
            )
    return scheduler
