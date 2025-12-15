import logging
from typing import Any

import httpx

from app.core.cache import cache_manager
from app.core.config import get_settings

from . import exceptions

logger = logging.getLogger("iiko.service")


class IikoService:
    TOKEN_CACHE_KEY = "iiko:access_token"
    TOKEN_TTL_BUFFER_SECONDS = 30

    def __init__(self):
        self.settings = get_settings()
        self._client = httpx.Client(base_url=self.settings.IIKO_API_BASE_URL, timeout=10.0)

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

    def _fetch_token(self) -> str:
        try:
            response = self._client.post("/api/1/access_token", json={"apiLogin": self.settings.IIKO_API_LOGIN})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("Unable to refresh Iiko access token")
            raise exceptions.ServiceError("Failed to obtain Iiko access token") from exc
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
        return self._fetch_token()

    def _auth_headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        token = self._get_token(force=force_refresh)
        return {"Authorization": f"Bearer {token}"}

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
        response = self._client.request(method, path, json=json, headers=headers)
        if response.status_code in (401, 403) and retry:
            headers = self._auth_headers(force_refresh=True)
            response = self._client.request(method, path, json=json, headers=headers)
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
        return response.json()

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
