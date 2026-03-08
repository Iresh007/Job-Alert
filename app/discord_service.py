from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Response

from app.db import SessionLocal, init_db
from app.discord_bot import DiscordBotService
from app.scan_queue import ScanQueueService
from app.settings_manager import get_profile, update_profile


app = FastAPI(title="Job Alert Discord Bot", version="1.0.0")
_bot: DiscordBotService | None = None
_queue = ScanQueueService()
_started_at = datetime.now(timezone.utc)


def _read_profile_with_new_session() -> dict:
    db = SessionLocal()
    try:
        return get_profile(db)
    finally:
        db.close()


def _write_profile_with_new_session(payload: dict) -> dict:
    db = SessionLocal()
    try:
        return update_profile(db, payload)
    finally:
        db.close()


def _enqueue_scan_with_new_session(**kwargs) -> tuple[dict, bool]:
    db = SessionLocal()
    try:
        request, created = _queue.enqueue(db, **kwargs)
        return _queue.to_dict(request), created
    finally:
        db.close()


def _get_scan_request_with_new_session(request_id: str) -> dict | None:
    db = SessionLocal()
    try:
        request = _queue.get_request(db, request_id)
        return _queue.to_dict(request) if request else None
    finally:
        db.close()


@app.on_event("startup")
async def startup() -> None:
    global _bot
    init_db()
    _bot = DiscordBotService(
        get_profile=_read_profile_with_new_session,
        update_profile=_write_profile_with_new_session,
        enqueue_scan=_enqueue_scan_with_new_session,
        get_scan_request=_get_scan_request_with_new_session,
    )
    await _bot.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    global _bot
    if _bot:
        await _bot.stop()
        _bot = None


@app.get("/health")
def health(response: Response) -> dict:
    if not _bot:
        response.status_code = 503
        return {"status": "unavailable", "reason": "bot_not_started"}
    snapshot = _bot.health_snapshot()
    boot_grace = datetime.now(timezone.utc) - _started_at < timedelta(seconds=60)
    response.status_code = 200 if snapshot.get("healthy") or boot_grace else 503
    if not snapshot.get("healthy") and boot_grace:
        snapshot["status"] = "starting"
    return snapshot
