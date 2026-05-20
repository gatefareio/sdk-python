"""Claim retry against /p/_claim/<id> (Gatefare's free-retry budget).

After a successful on-chain settle, if upstream returned 5xx the
buyer gets up to 10 retries within 24 hours via this endpoint.
The SDK retries up to DEFAULT_RETRY_BUDGET times internally with
exponential backoff; consumers don't see the loop.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .errors import GatefareApiError

DEFAULT_RETRY_BUDGET = 3


@dataclass
class ClaimContext:
    base_url: str
    http: httpx.Client


@dataclass
class ClaimRetryResult:
    status: int
    headers: dict[str, str]
    body: bytes
    content_type: str


def retry_claim(ctx: ClaimContext, claim_id: str) -> ClaimRetryResult:
    """One retry attempt. Raises GatefareApiError on 410/404/400."""
    url = f"{ctx.base_url}/p/_claim/{claim_id}"
    r = ctx.http.get(url)

    if r.status_code == 410:
        raise GatefareApiError(
            410, "CLAIM_EXHAUSTED",
            "Claim retry budget exhausted (10 attempts used or 24h elapsed). "
            "Contact the publisher with the claim id for an off-chain refund.",
        )
    if r.status_code == 404:
        raise GatefareApiError(404, "CLAIM_NOT_FOUND", f"No claim {claim_id}")
    if r.status_code == 400:
        raise GatefareApiError(400, "CLAIM_BAD_FORMAT", r.text or "Malformed claim id")

    headers = {k.lower(): v for k, v in r.headers.items()}
    return ClaimRetryResult(
        status=r.status_code,
        headers=headers,
        body=r.content,
        content_type=headers.get("content-type", "application/octet-stream"),
    )


def is_retryable_status(status: int) -> bool:
    """5xx + 408 + 429. Anything else is semantic / redirect — not
    the SDK's problem."""
    if 500 <= status < 600:
        return True
    if status in (408, 429):
        return True
    return False


def backoff_seconds(attempt: int) -> float:
    """1s, 2s, 4s, capped at 4s."""
    return min(4.0, 2 ** (attempt - 1))
