"""Regression for v0.1.1: get_api() must surface publisher.reputation
and sample_response end-to-end. v0.1.0 silently dropped both, leaving
SDK consumers unable to read trust signals before paying — exactly
the use case the backend's BACKLOG #46/#47 features were built for.
Matches the @gatefare/client@0.1.1 hot-fix in the TypeScript SDK."""

import httpx
from pytest_httpx import HTTPXMock

from gatefare.catalog import CatalogContext, get_api

BASE = "https://example-gatefare"

SAMPLE_DETAIL = {
    "slug": "weather-now",
    "urlName": "weather-now",
    "handle": "alice",
    "name": "Weather Now",
    "description": "Real-time weather.",
    "price": "$0.01",
    "network": "eip155:8453",
    "networkName": "Base",
    "testnet": False,
    "proxyUrl": "/p/alice/weather-now",
    "categories": ["weather"],
    "tags": ["realtime"],
    "publisher": {
        "handle": "alice",
        "displayName": "Alice",
        "verificationTier": None,
        "reputation": {
            "tenureMonths": 8,
            "established": True,
            "lifetimeSuccessCalls": 1_250_000,
            "topContributor": True,
            "averageRating": 4.7,
            "reviewCount": 42,
            "highlyRated": True,
            "activeApis": 3,
            "computedAt": 1_716_000_000_000,
        },
    },
    "sampleResponse": '{"temperature_c": 21.3, "conditions": "sunny"}',
}


def _ctx(client: httpx.Client) -> CatalogContext:
    return CatalogContext(base_url=BASE, http=client)


def test_get_api_surfaces_publisher_reputation(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/weather-now",
        json=SAMPLE_DETAIL,
    )
    with httpx.Client() as client:
        api = get_api(_ctx(client), "weather-now")
    assert api is not None
    assert api.publisher is not None
    assert api.publisher.handle == "alice"
    rep = api.publisher.reputation
    assert rep is not None
    assert rep.established is True
    assert rep.top_contributor is True
    assert rep.highly_rated is True
    assert rep.active_apis == 3
    assert rep.lifetime_success_calls == 1_250_000


def test_get_api_surfaces_sample_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/weather-now",
        json=SAMPLE_DETAIL,
    )
    with httpx.Client() as client:
        api = get_api(_ctx(client), "weather-now")
    assert api.sample_response == '{"temperature_c": 21.3, "conditions": "sunny"}'


def test_get_api_handles_legacy_listings(httpx_mock: HTTPXMock):
    legacy = {**SAMPLE_DETAIL, "publisher": None, "sampleResponse": None}
    httpx_mock.add_response(url=f"{BASE}/api/catalog/legacy", json=legacy)
    with httpx.Client() as client:
        api = get_api(_ctx(client), "legacy")
    assert api.publisher is None
    assert api.sample_response is None
