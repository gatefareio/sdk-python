"""Public dataclasses returned by the SDK.

Plain `@dataclass` over Pydantic for two reasons:
  1. Zero extra dependency at install time. Pydantic v2 is a heavy
     install (compiled Rust core), and we want the SDK to be cheap to
     pull into a slim agent runtime.
  2. The shape is fixed and tiny — we don't need validation magic on
     top of standard Python typing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


# CAIP-2 chain identifiers Gatefare currently supports. Widens as the
# marketplace onboards more networks; consumers should not pattern-
# match on the literal, just pass it through.
GatefareNetwork = Literal["eip155:8453", "eip155:84532"]


class SpendCaps(TypedDict, total=False):
    """Optional caps applied across every paid call. Both default to
    sane production values (1.00 USDC per call, 10.00 USDC per UTC
    day) — set them explicitly to tighten.
    """

    per_call_usdc: float
    per_day_usdc: float


@dataclass
class AccountReputation:
    """Positive-only publisher trust badges.

    Returned on get_api() detail responses (catalog list endpoints
    omit them for payload size). New accounts have all booleans
    false — treat absence of badges as "no signal yet", NOT as a
    warning. Thresholds are env-tunable server-side.
    """

    tenure_months: int
    established: bool
    lifetime_success_calls: int
    top_contributor: bool
    average_rating: float | None
    review_count: int
    highly_rated: bool
    active_apis: int
    computed_at: int


@dataclass
class PublisherInfo:
    """Publisher record attached to a catalog detail response."""

    handle: str | None
    display_name: str | None
    verification_tier: str | None
    reputation: AccountReputation | None = None


@dataclass
class CatalogApi:
    """One catalog listing returned by list_catalog / get_api.

    The fields up to `tags` are present on both endpoints. The fields
    below (`publisher`, `sample_response`) are populated by get_api()
    only — the list endpoint omits them to keep response sizes small.
    Both are typed as Optional so type-checked code on the list path
    keeps working without narrowing.
    """

    slug: str
    url_name: str | None
    handle: str | None
    name: str
    description: str
    price: str
    price_usdc: float
    network: str
    network_name: str
    testnet: bool
    proxy_url: str
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    # Detail-only fields. None when missing (list response) AND when
    # the wire returned null (legacy listing without a sample). The
    # distinction rarely matters to callers — both mean "not
    # available, don't render".
    publisher: PublisherInfo | None = None
    sample_response: str | None = None


@dataclass
class CallApiResult:
    """Result of a paid (or pass-through) API call.

    `data` is a parsed object for JSON responses, a string for text
    responses, and raw bytes otherwise. `status` mirrors the upstream
    API's HTTP code — non-2xx is surfaced here rather than raised so
    callers can handle 4xx semantics without try/except.
    """

    status: int
    headers: dict[str, str]
    data: Any
    paid_usdc: float
    claim_id: str | None
    settle_tx_hash: str | None


@dataclass
class WalletBalance:
    """USDC balance snapshot for the configured wallet."""

    usdc: float
    usdc_micros: int
    address: str
    network: str
