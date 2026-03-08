from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanRequest


ACTIVE_SCAN_STATUSES = {"queued", "running"}
TERMINAL_SCAN_STATUSES = {"completed", "failed"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScanQueueService:
    def get_request(self, db: Session, request_id: str) -> ScanRequest | None:
        return db.get(ScanRequest, request_id)

    def get_active_request(self, db: Session) -> ScanRequest | None:
        query = (
            select(ScanRequest)
            .where(ScanRequest.status.in_(ACTIVE_SCAN_STATUSES))
            .order_by(ScanRequest.requested_at.asc())
        )
        return db.scalars(query).first()

    def enqueue(
        self,
        db: Session,
        *,
        trigger_source: str,
        requested_by: str = "",
        requested_by_id: str = "",
        request_channel_id: str = "",
        request_guild_id: str = "",
        request_metadata: dict[str, Any] | None = None,
        dedupe_active: bool = True,
    ) -> tuple[ScanRequest, bool]:
        if dedupe_active:
            existing = self.get_active_request(db)
            if existing:
                return existing, False

        request = ScanRequest(
            id=str(uuid.uuid4()),
            trigger_source=trigger_source,
            requested_by=requested_by,
            requested_by_id=requested_by_id,
            request_channel_id=request_channel_id,
            request_guild_id=request_guild_id,
            request_metadata=request_metadata or {},
            status="queued",
            heartbeat_at=utcnow(),
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return request, True

    def reclaim_stale_requests(self, db: Session, *, stale_after_seconds: int = 600) -> int:
        stale_before = utcnow() - timedelta(seconds=stale_after_seconds)
        query = select(ScanRequest).where(
            ScanRequest.status == "running",
            ScanRequest.heartbeat_at.is_not(None),
            ScanRequest.heartbeat_at < stale_before,
        )
        stale_requests = db.scalars(query).all()
        for request in stale_requests:
            request.status = "queued"
            request.worker_id = ""
            request.error_message = "Recovered stale running request."
            request.claimed_at = None
            request.started_at = None
            request.finished_at = None
        if stale_requests:
            db.commit()
        return len(stale_requests)

    def claim_next(self, db: Session, *, worker_id: str) -> ScanRequest | None:
        query = select(ScanRequest).where(ScanRequest.status == "queued").order_by(ScanRequest.requested_at.asc())
        request = db.scalars(query).first()
        if not request:
            return None
        now = utcnow()
        request.status = "running"
        request.worker_id = worker_id
        request.claimed_at = now
        request.started_at = now
        request.finished_at = None
        request.heartbeat_at = now
        request.attempt_count += 1
        request.error_message = ""
        db.commit()
        db.refresh(request)
        return request

    def heartbeat(self, db: Session, request_id: str, *, worker_id: str) -> ScanRequest | None:
        request = self.get_request(db, request_id)
        if not request or request.worker_id != worker_id:
            return None
        request.heartbeat_at = utcnow()
        db.commit()
        db.refresh(request)
        return request

    def complete(self, db: Session, request_id: str, *, worker_id: str, result_payload: dict[str, Any]) -> ScanRequest | None:
        request = self.get_request(db, request_id)
        if not request or request.worker_id != worker_id:
            return None
        now = utcnow()
        request.status = "completed"
        request.finished_at = now
        request.heartbeat_at = now
        request.result_payload = result_payload
        request.error_message = ""
        db.commit()
        db.refresh(request)
        return request

    def fail(
        self,
        db: Session,
        request_id: str,
        *,
        worker_id: str,
        error_message: str,
        result_payload: dict[str, Any] | None = None,
    ) -> ScanRequest | None:
        request = self.get_request(db, request_id)
        if not request or request.worker_id != worker_id:
            return None
        now = utcnow()
        request.status = "failed"
        request.finished_at = now
        request.heartbeat_at = now
        request.error_message = error_message[:4000]
        request.result_payload = result_payload or {}
        db.commit()
        db.refresh(request)
        return request

    @staticmethod
    def to_dict(request: ScanRequest) -> dict[str, Any]:
        return {
            "id": request.id,
            "status": request.status,
            "trigger_source": request.trigger_source,
            "requested_by": request.requested_by,
            "requested_by_id": request.requested_by_id,
            "request_channel_id": request.request_channel_id,
            "request_guild_id": request.request_guild_id,
            "requested_at": request.requested_at,
            "claimed_at": request.claimed_at,
            "started_at": request.started_at,
            "finished_at": request.finished_at,
            "heartbeat_at": request.heartbeat_at,
            "worker_id": request.worker_id,
            "attempt_count": request.attempt_count,
            "error_message": request.error_message,
            "request_metadata": request.request_metadata or {},
            "result_payload": request.result_payload or {},
        }
