import httpx
import pytest
from pytest_httpx import HTTPXMock

from gatefare import GatefareApiError
from gatefare.claim import (
    ClaimContext,
    backoff_seconds,
    is_retryable_status,
    retry_claim,
)

BASE = "https://example-gatefare"


def _ctx(client: httpx.Client) -> ClaimContext:
    return ClaimContext(base_url=BASE, http=client)


def test_retry_returns_body_on_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/p/_claim/c1",
        json={"ok": True},
        headers={"Content-Type": "application/json"},
    )
    with httpx.Client() as client:
        r = retry_claim(_ctx(client), "c1")
    assert r.status == 200
    assert r.content_type == "application/json"


def test_retry_raises_exhausted_on_410(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/p/_claim/exhausted", status_code=410)
    with httpx.Client() as client, pytest.raises(GatefareApiError) as exc:
        retry_claim(_ctx(client), "exhausted")
    assert exc.value.status == 410
    assert exc.value.code == "CLAIM_EXHAUSTED"


def test_retry_raises_not_found_on_404(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/p/_claim/missing", status_code=404)
    with httpx.Client() as client, pytest.raises(GatefareApiError) as exc:
        retry_claim(_ctx(client), "missing")
    assert exc.value.status == 404
    assert exc.value.code == "CLAIM_NOT_FOUND"


def test_retry_raises_bad_format_on_400(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/p/_claim/bad", status_code=400, text="malformed")
    with httpx.Client() as client, pytest.raises(GatefareApiError) as exc:
        retry_claim(_ctx(client), "bad")
    assert exc.value.status == 400
    assert exc.value.code == "CLAIM_BAD_FORMAT"


def test_is_retryable_status():
    assert is_retryable_status(500) is True
    assert is_retryable_status(502) is True
    assert is_retryable_status(599) is True
    assert is_retryable_status(408) is True
    assert is_retryable_status(429) is True

    assert is_retryable_status(200) is False
    assert is_retryable_status(301) is False
    assert is_retryable_status(400) is False
    assert is_retryable_status(401) is False
    assert is_retryable_status(403) is False
    assert is_retryable_status(404) is False


def test_backoff_seconds_caps_at_4():
    assert backoff_seconds(1) == 1.0
    assert backoff_seconds(2) == 2.0
    assert backoff_seconds(3) == 4.0
    assert backoff_seconds(10) == 4.0


def test_gatefare_api_error_attrs():
    err = GatefareApiError(402, "FOO", "wat", "slug-1")
    assert err.status == 402
    assert err.code == "FOO"
    assert str(err) == "wat"
    assert err.slug == "slug-1"
