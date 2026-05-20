import httpx
import pytest
from pytest_httpx import HTTPXMock

from gatefare import GatefareApiError
from gatefare.catalog import CatalogContext, get_api, list_catalog

BASE = "https://example-gatefare"

SAMPLE_BODY = {
    "apis": [
        {
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
        },
        {
            "slug": "ai-image",
            "urlName": "ai-image",
            "handle": "bob",
            "name": "AI Image",
            "description": "Generate images.",
            "price": "$1.00",
            "network": "eip155:8453",
            "networkName": "Base",
            "testnet": False,
            "proxyUrl": "/p/bob/ai-image",
            "categories": ["ai"],
            "tags": ["images"],
        },
    ],
}


def _ctx(client: httpx.Client) -> CatalogContext:
    return CatalogContext(base_url=BASE, http=client)


def test_list_catalog_parses_apis(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/catalog", json=SAMPLE_BODY)
    with httpx.Client() as client:
        apis = list_catalog(_ctx(client))
    assert len(apis) == 2
    assert apis[0].slug == "weather-now"
    assert apis[0].price_usdc == 0.01
    assert apis[1].price_usdc == 1.0


def test_price_limit_filters_client_side(httpx_mock: HTTPXMock):
    # Server is called with q + price_max in the URL; we hand back the
    # full body and assert the SDK's defensive client-side filter trims.
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?q=weather&price_max=0.5",
        json=SAMPLE_BODY,
    )
    with httpx.Client() as client:
        apis = list_catalog(_ctx(client), query="weather", price_limit_usdc=0.5)
    assert len(apis) == 1
    assert apis[0].slug == "weather-now"


def test_wire_name_translation(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?category=weather&tag=realtime&price_max=0.25&includeTestnet=1&per_page=5",
        json={"apis": []},
    )
    with httpx.Client() as client:
        list_catalog(
            _ctx(client),
            category="weather",
            tag="realtime",
            include_testnet=True,
            limit=5,
            price_limit_usdc=0.25,
        )
    # If the URL above didn't match, httpx_mock raises.


def test_limit_capped_at_50(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog?per_page=50",
        json={"apis": []},
    )
    with httpx.Client() as client:
        list_catalog(_ctx(client), limit=999)


def test_list_catalog_throws_on_non_2xx(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/catalog", status_code=500, text="oops")
    with httpx.Client() as client, pytest.raises(GatefareApiError):
        list_catalog(_ctx(client))


def test_get_api_returns_listing(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/weather-now",
        json=SAMPLE_BODY["apis"][0],
    )
    with httpx.Client() as client:
        api = get_api(_ctx(client), "weather-now")
    assert api is not None
    assert api.slug == "weather-now"


def test_get_api_returns_none_on_404(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/unknown",
        status_code=404,
        json={"error": "API not found"},
    )
    with httpx.Client() as client:
        api = get_api(_ctx(client), "unknown")
    assert api is None


def test_get_api_throws_on_other_non_2xx(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/api/catalog/broken",
        status_code=500,
        text="err",
    )
    with httpx.Client() as client, pytest.raises(GatefareApiError):
        get_api(_ctx(client), "broken")
