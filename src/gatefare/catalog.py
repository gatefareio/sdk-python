"""Catalog reads against /api/catalog and /api/catalog/:slug.

The wire format is documented in the main Gatefare repo. Server-side
parameter names: q, category, tag, price_max, per_page, includeTestnet.
SDK-side names are friendlier (query, price_limit_usdc, limit) and
this module translates between the two.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from .errors import GatefareApiError
from .types import AccountReputation, CatalogApi, PublisherInfo


@dataclass
class CatalogContext:
    base_url: str
    http: httpx.Client
    personal_access_token: str | None = None

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.personal_access_token}"} if self.personal_access_token else {}


_PRICE_RE = re.compile(r"^\$?(\d+(?:\.\d+)?)$")


def _parse_price_usdc(price: str) -> float:
    m = _PRICE_RE.match(price.strip())
    return float(m.group(1)) if m else 0.0


def _raw_to_catalog_api(r: dict[str, Any]) -> CatalogApi:
    # Detail-only fields (get_api responses). The list endpoint omits
    # them, so we pass through opportunistically: present when the
    # wire provided them, None otherwise. Same semantics as the TS
    # SDK's @gatefare/client.
    publisher: PublisherInfo | None = None
    raw_pub = r.get("publisher")
    if isinstance(raw_pub, dict):
        rep_raw = raw_pub.get("reputation")
        reputation: AccountReputation | None = None
        if isinstance(rep_raw, dict):
            reputation = AccountReputation(
                tenure_months=int(rep_raw.get("tenureMonths") or 0),
                established=bool(rep_raw.get("established")),
                lifetime_success_calls=int(rep_raw.get("lifetimeSuccessCalls") or 0),
                top_contributor=bool(rep_raw.get("topContributor")),
                average_rating=rep_raw.get("averageRating"),
                review_count=int(rep_raw.get("reviewCount") or 0),
                highly_rated=bool(rep_raw.get("highlyRated")),
                active_apis=int(rep_raw.get("activeApis") or 0),
                computed_at=int(rep_raw.get("computedAt") or 0),
            )
        publisher = PublisherInfo(
            handle=raw_pub.get("handle"),
            display_name=raw_pub.get("displayName"),
            verification_tier=raw_pub.get("verificationTier"),
            reputation=reputation,
        )

    return CatalogApi(
        slug=r["slug"],
        url_name=r.get("urlName"),
        handle=r.get("handle"),
        name=r["name"],
        description=r.get("description") or "",
        price=r["price"],
        price_usdc=_parse_price_usdc(r["price"]),
        network=r["network"],
        network_name=r["networkName"],
        testnet=bool(r.get("testnet", False)),
        proxy_url=r["proxyUrl"],
        categories=list(r.get("categories") or []),
        tags=list(r.get("tags") or []),
        publisher=publisher,
        sample_response=r.get("sampleResponse"),
    )


def _build_query_string(
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    price_limit_usdc: float | None = None,
    include_testnet: bool = False,
    limit: int | None = None,
) -> str:
    """Translate SDK params to server wire names."""
    parts: dict[str, str] = {}
    if query:
        parts["q"] = query
    if category:
        parts["category"] = category
    if tag:
        parts["tag"] = tag
    if price_limit_usdc is not None and price_limit_usdc >= 0:
        parts["price_max"] = str(price_limit_usdc)
    if include_testnet:
        parts["includeTestnet"] = "1"
    if limit is not None:
        # Server caps per_page at 50; we cap further so a buggy caller
        # asking for 1000 doesn't trigger a 400.
        capped = max(1, min(50, limit))
        parts["per_page"] = str(capped)
    return f"?{urlencode(parts)}" if parts else ""


def list_catalog(
    ctx: CatalogContext,
    *,
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    price_limit_usdc: float | None = None,
    include_testnet: bool = False,
    limit: int | None = None,
) -> list[CatalogApi]:
    """Search the public catalog. No wallet required."""
    qs = _build_query_string(
        query=query,
        category=category,
        tag=tag,
        price_limit_usdc=price_limit_usdc,
        include_testnet=include_testnet,
        limit=limit,
    )
    url = f"{ctx.base_url}/api/catalog{qs}"

    r = ctx.http.get(url, headers=ctx.auth_header)
    if r.status_code != 200:
        raise GatefareApiError(
            r.status_code,
            None,
            f"Catalog request failed: {r.status_code} {r.reason_phrase}",
        )

    body = r.json()
    apis = [_raw_to_catalog_api(a) for a in (body.get("apis") or [])]

    # Defensive client-side filters in case the server ignored the
    # corresponding wire parameter (regression belt).
    if price_limit_usdc is not None:
        apis = [a for a in apis if a.price_usdc <= price_limit_usdc]
    if limit is not None:
        apis = apis[: max(1, min(50, limit))]

    return apis


def get_api(ctx: CatalogContext, slug: str) -> CatalogApi | None:
    """Fetch one API by slug. Returns None on 404."""
    url = f"{ctx.base_url}/api/catalog/{slug}"
    r = ctx.http.get(url, headers=ctx.auth_header, follow_redirects=True)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise GatefareApiError(
            r.status_code, None,
            f"get_api failed: {r.status_code} {r.reason_phrase}", slug,
        )
    return _raw_to_catalog_api(r.json())
