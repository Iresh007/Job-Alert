from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Response

from app.db import SessionLocal, init_db
from app.discord_bot import DiscordBotService
from app.logging_utils import log_event
from app.scan_queue import ScanQueueService
from app.scan_worker import run_scan_worker
from app.settings_manager import get_profile, update_profile


app = FastAPI(title="Job Alert Discord Bot", version="1.0.0")
_bot: DiscordBotService | None = None
_queue = ScanQueueService()
_started_at = datetime.now(timezone.utc)
_worker_task = None
_worker_stop_event = None
_worker_healthy = False
_worker_last_error = ""


def _set_worker_unhealthy(error_message: str) -> None:
    global _worker_healthy, _worker_last_error
    _worker_healthy = False
    _worker_last_error = error_message
    log_event("embedded_scan_worker_unhealthy", level="warning", error=error_message)


def _set_worker_healthy() -> None:
    global _worker_healthy, _worker_last_error
    _worker_healthy = True
    _worker_last_error = ""


def _handle_worker_done(task) -> None:
    if task.cancelled():
        _set_worker_unhealthy("Embedded scan worker task cancelled.")
        return
    try:
        exc = task.exception()
    except BaseException as err:
        _set_worker_unhealthy(f"Embedded scan worker status check failed: {err}")
        return
    if exc:
        _set_worker_unhealthy(f"Embedded scan worker exited with error: {exc}")
    else:
        _set_worker_unhealthy("Embedded scan worker exited.")


async def _run_worker_forever(stop_event: asyncio.Event) -> None:
    retry_delay_seconds = 5
    while not stop_event.is_set():
        try:
            _set_worker_healthy()
            await run_scan_worker(stop_event)
            if stop_event.is_set():
                return
            _set_worker_unhealthy("Embedded scan worker stopped unexpectedly. Restarting.")
        except Exception as exc:
            if stop_event.is_set():
                return
            _set_worker_unhealthy(f"Embedded scan worker failed: {exc}")
        await asyncio.sleep(retry_delay_seconds)


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
    global _bot, _worker_task, _worker_stop_event
    init_db()
    _bot = DiscordBotService(
        get_profile=_read_profile_with_new_session,
        update_profile=_write_profile_with_new_session,
        enqueue_scan=_enqueue_scan_with_new_session,
        get_scan_request=_get_scan_request_with_new_session,
    )
    await _bot.start()
    _worker_stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_run_worker_forever(_worker_stop_event))
    _worker_task.add_done_callback(_handle_worker_done)


@app.on_event("shutdown")
async def shutdown() -> None:
    global _bot, _worker_task, _worker_stop_event
    if _bot:
        await _bot.stop()
        _bot = None
    if _worker_stop_event:
        _worker_stop_event.set()
    if _worker_task:
        try:
            await _worker_task
        except BaseException:
            pass
        _worker_task = None
    _worker_stop_event = None


@app.get("/health")
def health(response: Response) -> dict:
    if not _bot:
        response.status_code = 503
        return {"status": "unavailable", "reason": "bot_not_started"}
    snapshot = _bot.health_snapshot()
    snapshot["worker_healthy"] = _worker_healthy
    snapshot["worker_last_error"] = _worker_last_error
    boot_grace = datetime.now(timezone.utc) - _started_at < timedelta(seconds=60)
    overall_healthy = snapshot.get("healthy") and _worker_healthy
    response.status_code = 200
    if not overall_healthy and boot_grace:
        snapshot["status"] = "starting"
    elif not overall_healthy:
        snapshot["status"] = "degraded"
    return snapshot


@app.get("/")
def root() -> dict:
    return {"service": "job-alert-discord-bot", "health_path": "/health"}
