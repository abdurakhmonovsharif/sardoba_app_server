import httpx
import pytest

from app.services.iiko_service import IikoService
from app.services import exceptions


class DummyClient:
    def __init__(self, outcomes: list[object]):
        self.outcomes = outcomes
        self.timeout = httpx.Timeout(connect=1.0, read=1.0, write=1.0, pool=1.0)
        self.base_url = httpx.URL("http://example.com")
        self.calls = 0

    def request(self, method, path, json=None, headers=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(status_code: int = 200, json_body: dict | None = None, method: str = "POST"):
    request = httpx.Request(method, "http://example.com")
    return httpx.Response(status_code, request=request, json=json_body or {})


def test_retries_on_connect_error_idempotent_post():
    # First attempt fails on connect, second succeeds.
    client = DummyClient(
        [
            httpx.ConnectError("connect fail", request=httpx.Request("POST", "http://example.com")),
            _response(json_body={"ok": True}),
        ]
    )
    service = IikoService()
    service._client = client  # type: ignore[attr-defined]

    resp = service._send_request(
        "POST",
        "/api/1/loyalty/iiko/customer/info",
        json={"phone": "+99890"},
        headers={},
    )

    assert resp.status_code == 200
    assert client.calls == 2


def test_non_idempotent_post_does_not_retry_on_read_timeout():
    client = DummyClient(
        [
            httpx.ReadTimeout("read", request=httpx.Request("POST", "http://example.com")),
            _response(json_body={"should_not_reach": True}),
        ]
    )
    service = IikoService()
    service._client = client  # type: ignore[attr-defined]

    with pytest.raises(exceptions.ServiceError):
        service._send_request(
            "POST",
            "/api/1/loyalty/iiko/customer/create_or_update",
            json={"phone": "+99890"},
            headers={},
        )

    assert client.calls == 1


def test_idempotent_post_retries_on_read_timeout_then_succeeds():
    client = DummyClient(
        [
            httpx.ReadTimeout("read", request=httpx.Request("POST", "http://example.com")),
            _response(json_body={"ok": True}),
        ]
    )
    service = IikoService()
    service._client = client  # type: ignore[attr-defined]

    resp = service._send_request(
        "POST",
        "/api/1/loyalty/iiko/customer/info",
        json={"phone": "+99890"},
        headers={},
    )

    assert resp.status_code == 200
    assert client.calls == 2
