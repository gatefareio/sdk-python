"""Exception types raised by the SDK.

Two named exceptions cover everything the consumer needs to branch on:

  - SpendCapError    — refused locally BEFORE any signature was made.
                       The wallet never produced an authorization. Safe
                       to retry with a higher cap if intended.

  - GatefareApiError — Gatefare returned a non-2xx that the SDK cannot
                       recover from (unknown slug, exhausted claim,
                       malformed quote).

Non-2xx upstream responses AFTER a successful settle are surfaced as
the `status` field on `CallApiResult` rather than raised, so callers
can branch on status without try/except wrapping.
"""

from __future__ import annotations


class SpendCapError(Exception):
    """The SDK refused a call locally because it would exceed a
    configured spend cap. The wallet never signed anything; no USDC
    moved.

    Attributes:
        reason: "per_call_cap_exceeded" or "per_day_cap_exceeded"
        attempted_usdc: USDC amount that triggered the refusal
        cap_usdc: cap that the attempt exceeded
    """

    def __init__(self, reason: str, attempted_usdc: float, cap_usdc: float) -> None:
        self.reason = reason
        self.attempted_usdc = attempted_usdc
        self.cap_usdc = cap_usdc
        super().__init__(
            f"SDK-local spend cap ({cap_usdc:.2f} USDC) would be exceeded "
            f"by a call requesting {attempted_usdc:.2f} USDC ({reason}). "
            f"Raise the cap explicitly in the call or adjust the constructor settings."
        )


class GatefareApiError(Exception):
    """A non-2xx response from Gatefare that the SDK cannot recover
    from automatically.

    Attributes:
        status: HTTP status code from the failed response
        code: machine-readable code from the response body (e.g.
              "CLAIM_EXHAUSTED"), or None if the server did not send one
        slug: the API slug involved, if relevant
    """

    def __init__(
        self,
        status: int,
        code: str | None,
        message: str,
        slug: str | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.slug = slug
        super().__init__(message)
