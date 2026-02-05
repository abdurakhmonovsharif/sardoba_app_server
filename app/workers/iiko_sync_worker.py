from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.core.cache import RedisCacheBackend, cache_manager
from app.core.db import session_scope
from app.core.locking import make_lock
from app.models import User
from app.services import AuthService, IikoProfileSyncService, IikoService
from app.services import exceptions as service_exceptions
from app.services.iiko_sync_job_service import IikoSyncJobService

logger = logging.getLogger("iiko.sync_worker")


class IikoSyncWorker:
    LOCK_TTL_SECONDS = 45
    LOCK_WAIT_SECONDS = 0.2
    LOCK_RETRY_INTERVAL_SECONDS = 0.05
    POLL_INTERVAL_SECONDS = 1.0
    STUCK_JOB_TIMEOUT_SECONDS = 120
    STUCK_RECOVERY_LIMIT = 200
    METRICS_LOG_INTERVAL_SECONDS = 60

    def __init__(self, *, worker_id: str | None = None, batch_size: int = 20):
        self.worker_id = worker_id or f"iiko-sync-worker-{uuid.uuid4().hex[:8]}"
        self.batch_size = max(1, batch_size)
        backend = cache_manager.get_backend()
        self._redis_client = backend.client if isinstance(backend, RedisCacheBackend) else None
        self._metrics: dict[str, int] = {
            "iterations": 0,
            "claimed": 0,
            "processed": 0,
            "success": 0,
            "retry": 0,
            "transient_retry": 0,
            "lock_busy": 0,
            "stuck_recovered": 0,
        }
        self._last_metrics_log = time.monotonic()

    def run_forever(self) -> None:
        logger.info("iiko_sync_worker_started", extra={"worker_id": self.worker_id, "batch_size": self.batch_size})
        while True:
            self._inc_metric("iterations")
            processed = self.run_once()
            if processed == 0:
                time.sleep(self.POLL_INTERVAL_SECONDS)
            self._log_metrics_if_due()

    def run_once(self) -> int:
        with session_scope() as session:
            service = IikoSyncJobService(session)
            recovered = service.recover_stuck_jobs(
                stale_after_seconds=self.STUCK_JOB_TIMEOUT_SECONDS,
                limit=self.STUCK_RECOVERY_LIMIT,
            )
            jobs = service.claim_due_jobs(worker_id=self.worker_id, limit=self.batch_size)
        if recovered:
            self._inc_metric("stuck_recovered", recovered)
            logger.warning(
                "iiko_sync_worker_recovered_stuck_jobs",
                extra={"worker_id": self.worker_id, "count": recovered},
            )
        if not jobs:
            return 0

        self._inc_metric("claimed", len(jobs))
        for job in jobs:
            self._process_job(job.id)
        self._inc_metric("processed", len(jobs))
        return len(jobs)

    def _process_job(self, job_id: int) -> None:
        with session_scope() as session:
            service = IikoSyncJobService(session)
            job = service.get_claimed_job(job_id=job_id, worker_id=self.worker_id)
            if not job:
                return
            operation = job.operation
            user_id = job.user_id
            phone = job.phone
            payload = dict(job.payload or {})

        lock_key = self._per_user_lock_key(user_id=user_id, phone=phone)
        lock = make_lock(
            lock_key,
            redis_client=self._redis_client,
            ttl_seconds=self.LOCK_TTL_SECONDS,
            wait_timeout=self.LOCK_WAIT_SECONDS,
            retry_interval=self.LOCK_RETRY_INTERVAL_SECONDS,
            log=logger,
        )

        with lock.hold() as acquired:
            if not acquired:
                self._inc_metric("lock_busy")
                with session_scope() as session:
                    IikoSyncJobService(session).requeue_lock_busy(
                        job_id=job_id,
                        worker_id=self.worker_id,
                        reason="user_lock_busy",
                    )
                return
            try:
                self._execute_operation(operation=operation, user_id=user_id, phone=phone, payload=payload)
            except service_exceptions.TransientServiceError as exc:
                self._inc_metric("transient_retry")
                with session_scope() as session:
                    IikoSyncJobService(session).requeue_transient(
                        job_id=job_id,
                        worker_id=self.worker_id,
                        reason=str(exc),
                        delay_seconds=exc.retry_after_seconds,
                    )
                return
            except Exception as exc:
                self._inc_metric("retry")
                logger.exception("iiko_sync_job_failed", extra={"job_id": job_id, "operation": operation})
                with session_scope() as session:
                    IikoSyncJobService(session).mark_retry(
                        job_id=job_id,
                        worker_id=self.worker_id,
                        error=str(exc),
                    )
                return

        with session_scope() as session:
            IikoSyncJobService(session).mark_success(job_id=job_id, worker_id=self.worker_id)
        self._inc_metric("success")

    def _execute_operation(
        self,
        *,
        operation: str,
        user_id: int | None,
        phone: str | None,
        payload: dict[str, Any],
    ) -> None:
        if operation == IikoSyncJobService.OP_SYNC_USER:
            self._execute_user_sync(user_id=user_id, create_if_missing=bool(payload.get("create_if_missing", False)))
            return
        if operation == IikoSyncJobService.OP_FLUSH_PROFILE:
            self._execute_profile_flush(user_id=user_id)
            return
        if operation == IikoSyncJobService.OP_MARK_DELETED:
            self._execute_mark_deleted(phone=phone, payload=payload)
            return
        raise ValueError(f"Unsupported iiko sync operation: {operation}")

    def _execute_user_sync(self, *, user_id: int | None, create_if_missing: bool) -> None:
        if user_id is None:
            raise ValueError("sync_user operation requires user_id")
        with session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if not user or user.is_deleted:
                return
            sync_result = AuthService(session).sync_user_from_iiko(
                user,
                create_if_missing=create_if_missing,
                admin_sync=False,
            )
            if not sync_result.ok:
                raise RuntimeError(sync_result.error or "iiko_sync_failed")
            if user.pending_iiko_profile_update:
                IikoProfileSyncService(session).flush_pending_updates(user)

    def _execute_profile_flush(self, *, user_id: int | None) -> None:
        if user_id is None:
            raise ValueError("flush_profile operation requires user_id")
        with session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if not user or user.is_deleted or not user.pending_iiko_profile_update:
                return
            IikoProfileSyncService(session).flush_pending_updates(user)

    def _execute_mark_deleted(self, *, phone: str | None, payload: dict[str, Any]) -> None:
        if not phone:
            raise ValueError("mark_deleted operation requires phone")
        iiko_payload = payload.get("iiko_payload")
        if not isinstance(iiko_payload, dict):
            raise ValueError("mark_deleted operation requires iiko_payload")
        IikoService().create_or_update_customer(phone=phone, payload_extra=iiko_payload)

    def _per_user_lock_key(self, *, user_id: int | None, phone: str | None) -> str:
        if user_id is not None:
            return f"iiko:sync:job:user:{user_id}"
        if phone:
            return f"iiko:sync:job:phone:{phone}"
        return "iiko:sync:job:unknown"

    def _inc_metric(self, key: str, amount: int = 1) -> None:
        self._metrics[key] = self._metrics.get(key, 0) + amount

    def _log_metrics_if_due(self) -> None:
        now = time.monotonic()
        if now - self._last_metrics_log < self.METRICS_LOG_INTERVAL_SECONDS:
            return
        self._last_metrics_log = now
        logger.info(
            "iiko_sync_worker_metrics",
            extra={"worker_id": self.worker_id, **self._metrics},
        )


def main() -> None:
    IikoSyncWorker().run_forever()


if __name__ == "__main__":
    main()
