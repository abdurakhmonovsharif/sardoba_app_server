import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any

import httpx

from app.core.cache import RedisCacheBackend, cache_manager
from app.core.config import get_settings

from . import exceptions

logger = logging.getLogger("iiko.service")


class IikoService:
    TOKEN_CACHE_KEY = "iiko:access_token"
    TOKEN_TTL_BUFFER_SECONDS = 30
    TOKEN_FETCH_TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=12.0)
    TOKEN_LOCK_KEY = "iiko:access_token:lock"
    TOKEN_LOCK_TTL_SECONDS = 15
    TOKEN_LOCK_WAIT_SECONDS = 5
    TOKEN_LOCK_SLEEP_SECONDS = 0.05

    def __init__(self):
        self.settings = get_settings()
        self._client = httpx.Client(base_url=self.settings.IIKO_API_BASE_URL, timeout=httpx.Timeout(5.0))
        self._local_token_lock = threading.Lock()
        # Detect backend once to decide lock strategy
        self._cache_backend = cache_manager.get_backend()
        if self.settings.ENVIRONMENT.lower() == "production" and not isinstance(
            self._cache_backend, RedisCacheBackend
        ):
            logger.warning(
                "Redis cache backend is not configured in production; token cache will be per-process. "
                "Set REDIS_URL to enable cluster-wide token sharing."
            )

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
                # NX + EX acts as a lightweight distributed mutex
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
                    # Release only if still owned by us (best-effort, non-atomic)
                    current = self._cache_backend.client.get(self.TOKEN_LOCK_KEY)
                    if current and current.decode("utf-8") == lock_value:
                        self._cache_backend.client.delete(self.TOKEN_LOCK_KEY)
                except Exception:  # pragma: no cover - logging only
                    logger.debug("Failed to release Redis token lock", exc_info=True)
            else:
                self._local_token_lock.release()

    def _fetch_token(self) -> str:
        attempts = 2
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.post(
                    "/api/1/access_token",
                    json={"apiLogin": self.settings.IIKO_API_LOGIN},
                    timeout=self.TOKEN_FETCH_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
                token = payload.get("token")
                if not token:
                    raise exceptions.ServiceError("Iiko access token missing in response")
                ttl = self._extract_ttl(payload)
                self._set_cached_token(token, ttl)
                return token
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "Iiko access_token request timed out (attempt %s/%s)", attempt, attempts
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.exception("Unable to refresh Iiko access token")
                break
            time.sleep(0.2 * attempt)
        raise exceptions.ServiceError("Failed to obtain Iiko access token") from last_exc

    def _get_token(self, *, force: bool = False) -> str:
        if not force:
            token = self._get_cached_token()
            if token:
                return token
        with self._token_lock() as acquired:
            # If we failed to obtain the lock, still attempt fetch but avoid double work if cache filled meanwhile
            if not force:
                cached = self._get_cached_token()
                if cached:
                    return cached
            if not acquired:
                logger.debug("Proceeding to fetch token without lock (lock not acquired in time)")
            return self._fetch_token()

    def _auth_headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        token = self._get_token(force=force_refresh)
        return {"Authorization": f"Bearer {token}"}

    def _send_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str],
    ) -> httpx.Response:
        try:
            return self._client.request(method, path, json=json, headers=headers)
        except httpx.RequestError as exc:
            if isinstance(exc, httpx.TimeoutException):
                logger.warning("Iiko request %s %s timed out", method, path)
                raise exceptions.ServiceError("Iiko request timed out") from exc
            logger.warning("Iiko request %s %s failed: %s", method, path, exc)
            raise exceptions.ServiceError("Iiko request failed") from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        headers = self._auth_headers()
        logger.debug("Iiko request %s %s %s", method, path, json)
        response = self._send_request(method, path, json=json, headers=headers)
        if response.status_code in (401, 403) and retry:
            headers = self._auth_headers(force_refresh=True)
            response = self._send_request(method, path, json=json, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Iiko request %s %s failed (%s): %s",
                method,
                path,
                exc.response.status_code,
                exc.response.text,
            )
            raise
        if not response.content:
            return {}
        payload = response.json()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Iiko response %s %s -> %s", method, path, payload)
        return payload

    def get_customer_by_phone(self, phone: str) -> dict[str, Any] | None:
        payload = {"organizationId": self.settings.IIKO_ORGANIZATION_ID, "phone": phone, "type": "phone"}
        try:
            return self._request("POST", "/api/1/loyalty/iiko/customer/info", json=payload)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (404, 400):
                logger.debug("Iiko customer lookup %s returned %s", phone, status)
                return None
            raise exceptions.ServiceError("Failed to fetch Iiko customer info") from exc

    def create_or_update_customer(self, *, phone: str, payload_extra: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "organizationId": self.settings.IIKO_ORGANIZATION_ID,
            "phone": phone,
        }
        if payload_extra:
            body.update(payload_extra)
        body.setdefault("comment", "CASHBACK MOBILE APP CLIENT")
        try:
            return self._request("POST", "/api/1/loyalty/iiko/customer/create_or_update", json=body)
        except httpx.HTTPStatusError as exc:
            raise exceptions.ServiceError("Unable to create or update Iiko customer") from exc

    def add_card(self, *, customer_id: str, card_number: str, card_track: str) -> dict[str, Any]:
        payload = {
            "organizationId": self.settings.IIKO_ORGANIZATION_ID,
            "customerId": customer_id,
            "cardTrack": card_track,
            "cardNumber": card_number,
        }
        try:
            return self._request("POST", "/api/1/loyalty/iiko/customer/card/add", json=payload)
        except httpx.HTTPStatusError as exc:
            raise exceptions.ServiceError("Unable to add card to Iiko customer") from exc
