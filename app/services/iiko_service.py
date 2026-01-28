import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Optional

import httpx

from app.core.cache import RedisCacheBackend, cache_manager
from app.core.config import get_settings
from app.core.locking import make_lock
from app.core.observability import ensure_correlation_id, get_correlation_id

from . import exceptions

logger = logging.getLogger("iiko.service")


class IikoService:
    TOKEN_CACHE_KEY = "iiko:access_token"
    TOKEN_TTL_BUFFER_SECONDS = 30

    # Aggressive throttling protections
    CLIENT_TIMEOUT = httpx.Timeout(connect=2.0, read=8.0, write=2.0, pool=2.0)
    TOKEN_FETCH_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=3.0)
    TOKEN_LOCK_KEY = "iiko:access_token:lock"
    TOKEN_LOCK_TTL_SECONDS = 15
    TOKEN_LOCK_WAIT_SECONDS = 5
    TOKEN_LOCK_SLEEP_SECONDS = 0.05

    USER_LOCK_TTL_SECONDS = 20
    USER_LOCK_WAIT_SECONDS = 6
    ADMIN_LOCK_KEY = "iiko:lock:admin_sync"
    ADMIN_LOCK_TTL_SECONDS = 60

    IDEMPOTENT_PATHS = {
        "/api/1/access_token",
        "/api/1/loyalty/iiko/customer/info",  # iiko uses POST but it is a pure read
    }

    def __init__(self):
        self.settings = get_settings()
        self._client = httpx.Client(base_url=self.settings.IIKO_API_BASE_URL, timeout=self.CLIENT_TIMEOUT)
        self._local_token_lock = threading.Lock()
        self._cache_backend = cache_manager.get_backend()
        self._redis_client = self._cache_backend.client if isinstance(self._cache_backend, RedisCacheBackend) else None

        if self.settings.ENVIRONMENT.lower() == "production" and not isinstance(
            self._cache_backend, RedisCacheBackend
        ):
            logger.warning(
                "Redis cache backend is not configured in production; token cache will be per-process. "
                "Set REDIS_URL to enable cluster-wide token sharing."
            )

    # ---------------------- Token handling ---------------------- #

    def _cache_key(self) -> str:
        return self.TOKEN_CACHE_KEY

    def _get_cached_token(self) -> str | None:
        backend = cache_manager.get_backend()
        cached = backend.get(self._cache_key())
        if cached is None:
            return None
        return cached.decode("utf-8") if isinstance(cached, bytes) else cached

    def _set_cached_token(self, token: str, ttl_seconds: int) -> None:
        backend = cache_manager.get_backend()
        backend.set(self._cache_key(), token, max(ttl_seconds - self.TOKEN_TTL_BUFFER_SECONDS, 30))

    def _extract_ttl(self, payload: dict[str, Any]) -> int:
        for key in ("expiresIn", "expires", "expires_in"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return 3600

    @contextmanager
    def _token_lock(self):
        """
        Single-flight guard so only one worker/process refreshes the token at a time.
        Prefers Redis distributed lock when available; falls back to process-local lock.
        """
        lock_value = str(uuid.uuid4())
        acquired = False

        if isinstance(self._cache_backend, RedisCacheBackend):
            deadline = time.time() + self.TOKEN_LOCK_WAIT_SECONDS
            while time.time() < deadline:
                if self._cache_backend.client.set(
                    self.TOKEN_LOCK_KEY, lock_value, nx=True, ex=self.TOKEN_LOCK_TTL_SECONDS
                ):
                    acquired = True
                    break
                time.sleep(self.TOKEN_LOCK_SLEEP_SECONDS)
        else:
            acquired = self._local_token_lock.acquire(timeout=self.TOKEN_LOCK_WAIT_SECONDS)

        try:
            yield acquired
        finally:
            if not acquired:
                return
            if isinstance(self._cache_backend, RedisCacheBackend):
                try:
                    current = self._cache_backend.client.get(self.TOKEN_LOCK_KEY)
                    if current and current.decode("utf-8") == lock_value:
                        self._cache_backend.client.delete(self.TOKEN_LOCK_KEY)
                except Exception:  # pragma: no cover - logging only
                    logger.debug("Failed to release Redis token lock", exc_info=True)
            else:
                self._local_token_lock.release()

    def _fetch_token(self) -> str:
        response = self._send_request(
            "POST",
            "/api/1/access_token",
            json={"apiLogin": self.settings.IIKO_API_LOGIN},
            headers={},
            timeout_override=self.TOKEN_FETCH_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("token")
        if not token:
            raise exceptions.ServiceError("Iiko access token missing in response")
        ttl = self._extract_ttl(payload)
        self._set_cached_token(token, ttl)
        return token

    def _get_token(self, *, force: bool = False) -> str:
        if not force:
            token = self._get_cached_token()
            if token:
                return token
        with self._token_lock() as acquired:
            if not force:
                cached = self._get_cached_token()
                if cached:
                    return cached
            if not acquired:
                logger.debug("Proceeding to fetch token without lock (lock not acquired in time)")
            return self._fetch_token()

    def _auth_headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        token = self._get_token(force=force_refresh)
        return {
        "Authorization": f"Bearer {token}",
        "x-iiko-proxy-secret": self.settings.IIKO_PROXY_SECRET,
        "Content-Type": "application/json",
    }

    # ---------------------- Request layer ---------------------- #

    def _send_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str],
        timeout_override: httpx.Timeout | None = None,
    ) -> httpx.Response:
        attempts = 2  # 1 initial + 1 retry
        is_idempotent = self._is_idempotent(method, path)
        last_exc: httpx.RequestError | None = None

        for attempt in range(1, attempts + 1):
            corr = get_correlation_id() or ensure_correlation_id("iiko")
            started = time.perf_counter()
            logger.info(
                "iiko_request_start",
                extra={
                    "method": method,
                    "path": path,
                    "attempt": attempt,
                    "attempts": attempts,
                },
            )
            try:
                response = self._client.request(
                    method,
                    path,
                    json=json,
                    headers=headers,
                    timeout=timeout_override or self._client.timeout,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "iiko_request_success",
                    extra={
                        "method": method,
                        "path": path,
                        "attempt": attempt,
                        "elapsed_ms": round(elapsed_ms, 1),
                        "status_code": response.status_code,
                    },
                )
                return response
            except httpx.RequestError as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                stage = self._timeout_stage(exc)
                should_retry = self._should_retry(exc, is_idempotent)
                timeouts = timeout_override or self._client.timeout
                logger.warning(
                    "iiko_request_failed",
                    extra={
                        "method": method,
                        "path": path,
                        "stage": stage,
                        "exception": exc.__class__.__name__,
                        "attempt": attempt,
                        "attempts": attempts,
                        "elapsed_ms": round(elapsed_ms, 1),
                        "connect": timeouts.connect,
                        "read": timeouts.read,
                        "write": timeouts.write,
                        "pool": timeouts.pool,
                        "will_retry": should_retry and attempt < attempts,
                    },
                    exc_info=False,
                )
                last_exc = exc
                if not should_retry or attempt == attempts:
                    break
                time.sleep(self._retry_delay(attempt))

        assert last_exc is not None
        if isinstance(last_exc, httpx.TimeoutException):
            raise exceptions.ServiceError(f"Iiko request timed out ({last_exc.__class__.__name__})") from last_exc
        raise exceptions.ServiceError("Iiko request failed") from last_exc

    def _timeout_stage(self, exc: httpx.RequestError) -> str:
        mapping: list[tuple[type[BaseException], str]] = [
            (httpx.ConnectTimeout, "connect"),
            (httpx.ReadTimeout, "read"),
            (httpx.WriteTimeout, "write"),
            (httpx.PoolTimeout, "pool"),
            (httpx.ConnectError, "connect"),
        ]
        for exc_type, stage in mapping:
            if isinstance(exc, exc_type):
                return stage
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        return "unknown"

    def _should_retry(self, exc: httpx.RequestError, is_idempotent: bool) -> bool:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.WriteTimeout)):
            return True
        if isinstance(exc, httpx.ReadTimeout):
            return is_idempotent
        if isinstance(exc, httpx.TimeoutException):
            return is_idempotent
        return False

    def _is_idempotent(self, method: str, path: str) -> bool:
        return method.upper() in {"GET", "HEAD", "OPTIONS"} or path in self.IDEMPOTENT_PATHS

    def _retry_delay(self, attempt: int) -> float:
        base = 0.3
        return base * (2 ** (attempt - 1))

    # ---------------------- High-level request wrapper ---------------------- #

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        """
        Authenticates, sends, optionally retries on 401/403 with refreshed token,
        and returns parsed JSON (or {} if empty).
        """
        headers = self._auth_headers()
        response = self._send_request(method, path, json=json, headers=headers)
        if response.status_code in (401, 403) and retry:
            headers = self._auth_headers(force_refresh=True)
            response = self._send_request(method, path, json=json, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "iiko_request_http_error",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": exc.response.status_code,
                    "body": exc.response.text[:5000],
                },
            )
            raise
        if not response.content:
            return {}
        payload = response.json()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("iiko_response", extra={"method": method, "path": path, "payload": payload})
        return payload

    # ---------------------- User-scope locking ---------------------- #

    def _user_lock_key(self, phone: Optional[str] = None, customer_id: Optional[str] = None) -> str:
        if phone:
            return f"iiko:lock:customer:{phone}"
        if customer_id:
            return f"iiko:lock:customer_id:{customer_id}"
        return "iiko:lock:customer:unknown"

    def _with_user_lock(self, lock_key: str, func: Callable[[], Any]) -> Any:
        lock = make_lock(
            lock_key,
            redis_client=self._redis_client,
            ttl_seconds=self.USER_LOCK_TTL_SECONDS,
            wait_timeout=self.USER_LOCK_WAIT_SECONDS,
            retry_interval=0.05,
            log=logger,
        )
        with lock.hold() as acquired:
            if not acquired:
                raise exceptions.ServiceError("iiko user lock contention")
            return func()

    # ---------------------- Public API ---------------------- #

    def get_customer_by_phone(self, phone: str) -> dict[str, Any] | None:
        corr = ensure_correlation_id("iiko-sync")
        lock_key = self._user_lock_key(phone=phone)
        payload = {"organizationId": self.settings.IIKO_ORGANIZATION_ID, "phone": phone, "type": "phone"}

        def _call():
            try:
                return self._request("POST", "/api/1/loyalty/iiko/customer/info", json=payload)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (404, 400):
                    logger.debug("Iiko customer lookup %s returned %s", phone, status)
                    return None
                raise exceptions.ServiceError("Failed to fetch Iiko customer info") from exc

        return self._with_user_lock(lock_key, _call)

    def create_or_update_customer(self, *, phone: str, payload_extra: dict[str, Any] | None = None) -> dict[str, Any]:
        corr = ensure_correlation_id("iiko-sync")
        lock_key = self._user_lock_key(phone=phone)
        body: dict[str, Any] = {
            "organizationId": self.settings.IIKO_ORGANIZATION_ID,
            "phone": phone,
        }
        if payload_extra:
            body.update(payload_extra)
        body.setdefault("comment", "CASHBACK MOBILE APP CLIENT")

        def _call():
            try:
                return self._request("POST", "/api/1/loyalty/iiko/customer/create_or_update", json=body)
            except httpx.HTTPStatusError as exc:
                raise exceptions.ServiceError("Unable to create or update Iiko customer") from exc

        return self._with_user_lock(lock_key, _call)

    def add_card(self, *, customer_id: str, card_number: str, card_track: str) -> dict[str, Any]:
        corr = ensure_correlation_id("iiko-sync")
        lock_key = self._user_lock_key(customer_id=customer_id)
        payload = {
            "organizationId": self.settings.IIKO_ORGANIZATION_ID,
            "customerId": customer_id,
            "cardTrack": card_track,
            "cardNumber": card_number,
        }

        def _call():
            try:
                return self._request("POST", "/api/1/loyalty/iiko/customer/card/add", json=payload)
            except httpx.HTTPStatusError as exc:
                raise exceptions.ServiceError("Unable to add card to Iiko customer") from exc

        return self._with_user_lock(lock_key, _call)
