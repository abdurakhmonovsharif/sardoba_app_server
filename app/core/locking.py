import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from redis import Redis

# Default logger for locking; individual services can supply their own
logger = logging.getLogger("iiko.lock")


class DistributedLock:
    """
    Lightweight distributed mutex backed by Redis (NX + EX).
    Falls back to a process-local lock when Redis is unavailable.
    """

    def __init__(
        self,
        name: str,
        *,
        redis_client: Optional[Redis] = None,
        ttl_seconds: int = 20,
        wait_timeout: int = 5,
        retry_interval: float = 0.05,
        log: logging.Logger | None = None,
    ) -> None:
        self.name = name
        self.redis_client = redis_client
        self.ttl_seconds = ttl_seconds
        self.wait_timeout = wait_timeout
        self.retry_interval = retry_interval
        self._owner_token: str | None = None
        self._local_lock = threading.Lock()
        self._logger = log or logger

    def acquire(self) -> bool:
        deadline = time.time() + self.wait_timeout
        token = uuid.uuid4().hex
        self._owner_token = token
        contention_logged = False

        if self.redis_client:
            while time.time() < deadline:
                if self.redis_client.set(self.name, token, nx=True, ex=self.ttl_seconds):
                    self._logger.info("lock_acquired", extra={"lock": self.name})
                    return True
                if not contention_logged:
                    self._logger.warning("lock_contention", extra={"lock": self.name})
                    contention_logged = True
                time.sleep(self.retry_interval)
            self._logger.warning("lock_acquire_timeout", extra={"lock": self.name})
            return False

        # Fallback: local lock
        acquired = self._local_lock.acquire(timeout=self.wait_timeout)
        if acquired:
            self._logger.info("lock_acquired_local", extra={"lock": self.name})
        else:
            self._logger.warning("lock_contention_local", extra={"lock": self.name})
        return acquired

    def release(self) -> None:
        if self._owner_token is None:
            return
        if self.redis_client:
            try:
                release_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                self.redis_client.eval(release_script, 1, self.name, self._owner_token)
                self._logger.info("lock_released", extra={"lock": self.name})
            except Exception:
                self._logger.exception("lock_release_failed", extra={"lock": self.name})
        else:
            if self._local_lock.locked():
                self._local_lock.release()
                self._logger.info("lock_released_local", extra={"lock": self.name})
        self._owner_token = None

    @contextmanager
    def hold(self):
        acquired = self.acquire()
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


def make_lock(
    name: str,
    *,
    redis_client: Optional[Redis],
    ttl_seconds: int = 20,
    wait_timeout: int = 5,
    retry_interval: float = 0.05,
    log: logging.Logger | None = None,
) -> DistributedLock:
    return DistributedLock(
        name,
        redis_client=redis_client,
        ttl_seconds=ttl_seconds,
        wait_timeout=wait_timeout,
        retry_interval=retry_interval,
        log=log,
    )
