from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app.models import IikoSyncJob
from app.services import exceptions as service_exceptions
from app.services.iiko_service import IikoService
from app.services.iiko_sync_job_service import IikoSyncJobService
from app.workers.iiko_sync_worker import IikoSyncWorker


def test_iiko_token_refresh_is_non_blocking_when_lock_busy(monkeypatch):
    service = IikoService()
    monkeypatch.setattr(service, "_get_cached_token", lambda: None)

    @contextmanager
    def fake_token_lock():
        yield False

    monkeypatch.setattr(service, "_token_lock", fake_token_lock)

    with pytest.raises(service_exceptions.TransientServiceError) as exc_info:
        service._get_token()

    assert str(exc_info.value) == "iiko_token_refresh_in_progress"
    assert exc_info.value.retry_after_seconds == service.TOKEN_LOCK_RETRY_AFTER_SECONDS


def test_iiko_token_refresh_fetches_when_lock_acquired(monkeypatch):
    service = IikoService()
    monkeypatch.setattr(service, "_get_cached_token", lambda: None)
    monkeypatch.setattr(service, "_fetch_token", lambda: "token-123")

    @contextmanager
    def fake_token_lock():
        yield True

    monkeypatch.setattr(service, "_token_lock", fake_token_lock)

    assert service._get_token() == "token-123"


def test_recover_stuck_jobs_returns_running_jobs_to_pending(db_session):
    now = datetime.now(tz=timezone.utc)
    job = IikoSyncJob(
        operation=IikoSyncJobService.OP_SYNC_USER,
        user_id=123,
        phone="+998901111111",
        status=IikoSyncJobService.STATUS_RUNNING,
        payload={},
        attempt_count=2,
        max_attempts=8,
        next_retry_at=now,
        lock_owner="worker-a",
        locked_at=now - timedelta(minutes=5),
        last_attempt_at=now - timedelta(minutes=5),
    )
    db_session.add(job)
    db_session.commit()

    recovered = IikoSyncJobService(db_session).recover_stuck_jobs(stale_after_seconds=60)
    assert recovered == 1

    db_session.refresh(job)
    assert job.status == IikoSyncJobService.STATUS_PENDING
    assert job.lock_owner is None
    assert job.locked_at is None
    assert job.last_error == "stuck_job_recovered"


def test_worker_requeues_transient_failures_without_consuming_attempt(db_session, monkeypatch):
    phone = "+998909999901"
    service = IikoSyncJobService(db_session)
    job = service.enqueue_user_sync(
        user_id=777,
        phone=phone,
        create_if_missing=True,
        source="phase3_test",
    )
    claimed = service.claim_due_jobs(worker_id="worker-phase3", limit=100)
    assert job.id in {entry.id for entry in claimed}

    worker = IikoSyncWorker(worker_id="worker-phase3", batch_size=1)

    def fail_transient(**kwargs):
        raise service_exceptions.TransientServiceError("token_busy", retry_after_seconds=0.5)

    monkeypatch.setattr(worker, "_execute_operation", fail_transient)
    worker._process_job(job.id)

    db_session.expire_all()
    refreshed = db_session.query(IikoSyncJob).filter(IikoSyncJob.id == job.id).first()
    assert refreshed is not None
    assert refreshed.status == IikoSyncJobService.STATUS_PENDING
    assert refreshed.attempt_count == 0
    assert refreshed.lock_owner is None
    assert refreshed.locked_at is None
    assert refreshed.last_error == "token_busy"
