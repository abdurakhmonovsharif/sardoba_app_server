from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import IikoSyncJob

logger = logging.getLogger("iiko.sync_jobs")


class IikoSyncJobService:
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_FAILED = "failed"
    STATUS_SUCCESS = "success"
    STATUS_PAUSED = "paused"

    OP_SYNC_USER = "sync_user"
    OP_FLUSH_PROFILE = "flush_profile"
    OP_MARK_DELETED = "mark_deleted"

    DEFAULT_MAX_ATTEMPTS = 8
    BASE_BACKOFF_SECONDS = 15
    MAX_BACKOFF_SECONDS = 30 * 60
    LOCK_BUSY_DELAY_SECONDS = 2
    TRANSIENT_RETRY_DELAY_SECONDS = 1.0

    def __init__(self, db: Session):
        self.db = db

    def enqueue_user_sync(
        self,
        *,
        user_id: int,
        phone: str,
        create_if_missing: bool,
        source: str,
        auto_commit: bool = True,
    ) -> IikoSyncJob:
        payload: dict[str, Any] = {
            "create_if_missing": bool(create_if_missing),
            "source": source,
        }
        return self._enqueue(
            operation=self.OP_SYNC_USER,
            user_id=user_id,
            phone=phone,
            payload=payload,
            auto_commit=auto_commit,
        )

    def enqueue_profile_sync(
        self,
        *,
        user_id: int,
        phone: str,
        source: str,
        auto_commit: bool = True,
    ) -> IikoSyncJob:
        payload: dict[str, Any] = {"source": source}
        return self._enqueue(
            operation=self.OP_FLUSH_PROFILE,
            user_id=user_id,
            phone=phone,
            payload=payload,
            auto_commit=auto_commit,
        )

    def enqueue_delete_sync(
        self,
        *,
        user_id: int | None,
        phone: str,
        customer_id: str | None,
        full_name: str | None,
        source: str,
        auto_commit: bool = True,
    ) -> IikoSyncJob:
        iiko_payload: dict[str, Any] = {
            "isDeleted": True,
            "name": full_name or "",
            "phone": phone,
        }
        if customer_id:
            iiko_payload["id"] = customer_id
        return self._enqueue(
            operation=self.OP_MARK_DELETED,
            user_id=user_id,
            phone=phone,
            payload={"source": source, "iiko_payload": iiko_payload},
            auto_commit=auto_commit,
        )

    def _enqueue(
        self,
        *,
        operation: str,
        user_id: int | None,
        phone: str | None,
        payload: dict[str, Any] | None,
        auto_commit: bool,
        max_attempts: int | None = None,
    ) -> IikoSyncJob:
        now = self._now()
        target_attempts = max(1, max_attempts or self.DEFAULT_MAX_ATTEMPTS)

        existing = self._find_active_job(operation=operation, user_id=user_id, phone=phone)
        if existing:
            existing.payload = self._merge_payload(existing.payload, payload)
            existing.status = self.STATUS_PENDING
            existing.attempt_count = 0
            existing.next_retry_at = now
            existing.last_attempt_at = None
            existing.last_error = None
            existing.completed_at = None
            existing.lock_owner = None
            existing.locked_at = None
            existing.max_attempts = target_attempts
            self.db.add(existing)
            return self._finalize_enqueue(existing, auto_commit=auto_commit)

        job = IikoSyncJob(
            operation=operation,
            user_id=user_id,
            phone=phone,
            status=self.STATUS_PENDING,
            payload=payload or {},
            attempt_count=0,
            max_attempts=target_attempts,
            next_retry_at=now,
        )
        self.db.add(job)
        return self._finalize_enqueue(job, auto_commit=auto_commit)

    def _finalize_enqueue(self, job: IikoSyncJob, *, auto_commit: bool) -> IikoSyncJob:
        if auto_commit:
            self.db.commit()
            self.db.refresh(job)
        else:
            self.db.flush()
        return job

    def _find_active_job(self, *, operation: str, user_id: int | None, phone: str | None) -> IikoSyncJob | None:
        query = self.db.query(IikoSyncJob).filter(
            IikoSyncJob.operation == operation,
            IikoSyncJob.status.in_([self.STATUS_PENDING, self.STATUS_FAILED, self.STATUS_PAUSED]),
        )
        if user_id is not None:
            query = query.filter(IikoSyncJob.user_id == user_id)
        elif phone:
            query = query.filter(IikoSyncJob.user_id.is_(None), IikoSyncJob.phone == phone)
        return query.order_by(IikoSyncJob.id.desc()).first()

    def claim_due_jobs(self, *, worker_id: str, limit: int = 20) -> list[IikoSyncJob]:
        now = self._now()
        query = (
            self.db.query(IikoSyncJob)
            .filter(
                IikoSyncJob.status.in_([self.STATUS_PENDING, self.STATUS_FAILED]),
                IikoSyncJob.next_retry_at <= now,
                IikoSyncJob.attempt_count < IikoSyncJob.max_attempts,
            )
            .order_by(IikoSyncJob.next_retry_at.asc(), IikoSyncJob.id.asc())
        )
        try:
            query = query.with_for_update(skip_locked=True)
        except Exception:
            pass
        jobs = query.limit(max(1, limit)).all()
        if not jobs:
            return []

        for job in jobs:
            job.status = self.STATUS_RUNNING
            job.lock_owner = worker_id
            job.locked_at = now
            job.last_attempt_at = now
            self.db.add(job)
        self.db.commit()

        for job in jobs:
            self.db.refresh(job)
        return jobs

    def get_claimed_job(self, *, job_id: int, worker_id: str) -> IikoSyncJob | None:
        return (
            self.db.query(IikoSyncJob)
            .filter(
                IikoSyncJob.id == job_id,
                IikoSyncJob.status == self.STATUS_RUNNING,
                IikoSyncJob.lock_owner == worker_id,
            )
            .first()
        )

    def requeue_lock_busy(self, *, job_id: int, worker_id: str, reason: str) -> bool:
        job = self.get_claimed_job(job_id=job_id, worker_id=worker_id)
        if not job:
            return False
        now = self._now()
        job.status = self.STATUS_PENDING
        job.next_retry_at = now + timedelta(seconds=self.LOCK_BUSY_DELAY_SECONDS)
        job.lock_owner = None
        job.locked_at = None
        job.last_error = reason
        self.db.add(job)
        self.db.commit()
        return True

    def requeue_transient(
        self,
        *,
        job_id: int,
        worker_id: str,
        reason: str,
        delay_seconds: float | None = None,
    ) -> bool:
        job = self.get_claimed_job(job_id=job_id, worker_id=worker_id)
        if not job:
            return False
        now = self._now()
        delay = max(0.1, delay_seconds if delay_seconds is not None else self.TRANSIENT_RETRY_DELAY_SECONDS)
        job.status = self.STATUS_PENDING
        job.next_retry_at = now + timedelta(seconds=delay)
        job.lock_owner = None
        job.locked_at = None
        job.last_error = self._truncate_error(reason)
        self.db.add(job)
        self.db.commit()
        return True

    def mark_success(self, *, job_id: int, worker_id: str) -> bool:
        job = self.get_claimed_job(job_id=job_id, worker_id=worker_id)
        if not job:
            return False
        now = self._now()
        job.attempt_count = job.attempt_count + 1
        job.status = self.STATUS_SUCCESS
        job.completed_at = now
        job.last_error = None
        job.lock_owner = None
        job.locked_at = None
        self.db.add(job)
        self.db.commit()
        return True

    def mark_retry(self, *, job_id: int, worker_id: str, error: str) -> bool:
        job = self.get_claimed_job(job_id=job_id, worker_id=worker_id)
        if not job:
            return False
        now = self._now()
        attempts = job.attempt_count + 1
        job.attempt_count = attempts
        job.last_error = self._truncate_error(error)
        job.lock_owner = None
        job.locked_at = None
        if attempts >= job.max_attempts:
            job.status = self.STATUS_PAUSED
            job.next_retry_at = now
            logger.error(
                "iiko_sync_job_paused",
                extra={"job_id": job.id, "operation": job.operation, "attempts": attempts},
            )
        else:
            job.status = self.STATUS_FAILED
            job.next_retry_at = now + self._retry_delay(attempts)
        self.db.add(job)
        self.db.commit()
        return True

    def recover_stuck_jobs(self, *, stale_after_seconds: int, limit: int = 100) -> int:
        now = self._now()
        stale_after = max(1, stale_after_seconds)
        cutoff = now - timedelta(seconds=stale_after)
        query = (
            self.db.query(IikoSyncJob)
            .filter(
                IikoSyncJob.status == self.STATUS_RUNNING,
                IikoSyncJob.locked_at.isnot(None),
                IikoSyncJob.locked_at <= cutoff,
            )
            .order_by(IikoSyncJob.locked_at.asc(), IikoSyncJob.id.asc())
        )
        try:
            query = query.with_for_update(skip_locked=True)
        except Exception:
            pass
        stuck_jobs = query.limit(max(1, limit)).all()
        if not stuck_jobs:
            return 0

        for job in stuck_jobs:
            job.status = self.STATUS_PENDING
            job.next_retry_at = now
            job.lock_owner = None
            job.locked_at = None
            job.last_error = "stuck_job_recovered"
            self.db.add(job)
        self.db.commit()
        return len(stuck_jobs)

    def _retry_delay(self, attempts: int) -> timedelta:
        seconds = min(self.MAX_BACKOFF_SECONDS, self.BASE_BACKOFF_SECONDS * (2 ** max(attempts - 1, 0)))
        return timedelta(seconds=seconds)

    def _merge_payload(
        self,
        existing: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if existing:
            merged.update(existing)
        if incoming:
            merged.update(incoming)
        return merged

    def _truncate_error(self, value: str) -> str:
        return value[:2000]

    def _now(self) -> datetime:
        return datetime.now(tz=timezone.utc)
