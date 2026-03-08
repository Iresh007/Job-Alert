from __future__ import annotations

import asyncio
import os
import socket

from app.db import SessionLocal, init_db
from app.logging_utils import log_event
from app.pipeline import JobPipeline
from app.scan_queue import ScanQueueService


QUEUE_POLL_SECONDS = 5
HEARTBEAT_SECONDS = 10


async def _heartbeat_loop(queue: ScanQueueService, request_id: str, worker_id: str, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(HEARTBEAT_SECONDS)
        if stop_event.is_set():
            return
        db = SessionLocal()
        try:
            queue.heartbeat(db, request_id, worker_id=worker_id)
        finally:
            db.close()


async def _run_pipeline(pipeline: JobPipeline) -> dict:
    db = SessionLocal()
    try:
        return await pipeline.run(db)
    finally:
        db.close()


async def main() -> None:
    init_db()
    queue = ScanQueueService()
    pipeline = JobPipeline()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    log_event("scan_worker_started", worker_id=worker_id)

    while True:
        db = SessionLocal()
        try:
            reclaimed = queue.reclaim_stale_requests(db)
            if reclaimed:
                log_event("scan_requests_reclaimed", worker_id=worker_id, count=reclaimed, level="warning")
            request = queue.claim_next(db, worker_id=worker_id)
        finally:
            db.close()

        if not request:
            await asyncio.sleep(QUEUE_POLL_SECONDS)
            continue

        log_event(
            "scan_request_claimed",
            worker_id=worker_id,
            request_id=request.id,
            trigger_source=request.trigger_source,
            requested_by=request.requested_by,
        )

        heartbeat_stop = asyncio.Event()
        heartbeat_task = asyncio.create_task(_heartbeat_loop(queue, request.id, worker_id, heartbeat_stop))
        try:
            result = await _run_pipeline(pipeline)
            db = SessionLocal()
            try:
                queue.complete(db, request.id, worker_id=worker_id, result_payload=result)
            finally:
                db.close()
            log_event("scan_request_completed", worker_id=worker_id, request_id=request.id, result=result)
        except Exception as exc:
            db = SessionLocal()
            try:
                queue.fail(db, request.id, worker_id=worker_id, error_message=str(exc))
            finally:
                db.close()
            log_event("scan_request_failed", worker_id=worker_id, request_id=request.id, error=str(exc), level="error")
        finally:
            heartbeat_stop.set()
            try:
                await heartbeat_task
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
