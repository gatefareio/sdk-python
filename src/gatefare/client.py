"""Main Gatefare client class — Python mirror of @gatefare/client.

Three primary methods: list_catalog, call_api, check_balance. Plus
get_api as a single-listing helper. Everything else (signing, retry,
spend caps) is internal.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .catalog import CatalogContext, get_api as _get_api, list_catalog as _list_catalog
from .claim import (
    DEFAULT_RETRY_BUDGET,
    ClaimContext,
    backoff_seconds,
    is_retryable_status,
    retry_claim,
)
from .errors import GatefareApiError, SpendCapError
from .payment import PaymentRequirements, sign_eip3009_authorization
from .spend_cap import SpendCapManager
from .types import CallApiResult, CatalogApi, GatefareNetwork, SpendCaps, WalletBalance
from .wallet import WalletState, create_wallet_state, read_usdc_balance

DEFAULT_BASE_URL = "https://gatefare.io"


class Gatefare:
    """The public facade.

    Construct with at minimum a wallet_private_key if you intend to
    make paid calls. Read-only catalog access works without a wallet.

    Args:
        wallet_private_key: 0x-prefixed (or not) 32-byte hex private
            key. Required for `call_api` and `check_balance`.
        base_url: Override for staging or self-hosted environments.
            Defaults to https://gatefare.io.
        spend_caps: dict-like {per_call_usdc, per_day_usdc}.
            Defaults to {1.00, 10.00}.
        personal_access_token: Optional gfpat_... token for higher
            rate limits and write:catalog operations.
        http: Custom httpx.Client. Useful for tests + custom timeouts.
            We will not close it — your code owns it.
    """

    def __init__(
        self,
        *,
        wallet_private_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        spend_caps: SpendCaps | None = None,
        personal_access_token: str | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._pat = personal_access_token
        self._http = http or httpx.Client(timeout=30.0, follow_redirects=True)
        self._owns_http = http is None
        self._spend = SpendCapManager(caps=spend_caps)

        self._wallet: WalletState | None = None
        self._wallet_raw_key: str | None = None
        if wallet_private_key:
            self._wallet_raw_key = wallet_private_key
            self._wallet = create_wallet_state(wallet_private_key, "eip155:8453")

    # ── lifecycle ──────────────────────────────────────────────

    def close(self) -> None:
        """Release the underlying httpx.Client if we created it."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Gatefare:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ── public surface ─────────────────────────────────────────

    def list_catalog(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        price_limit_usdc: float | None = None,
        include_testnet: bool = False,
        limit: int | None = None,
    ) -> list[CatalogApi]:
        """Search the public catalog. No wallet required."""
        return _list_catalog(
            self._catalog_ctx(),
            query=query,
            category=category,
            tag=tag,
            price_limit_usdc=price_limit_usdc,
            include_testnet=include_testnet,
            limit=limit,
        )

    def get_api(self, slug: str) -> CatalogApi | None:
        """Fetch one API by slug. Returns None on 404."""
        return _get_api(self._catalog_ctx(), slug)

    def call_api(
        self,
        slug: str,
        *,
        method: str = "GET",
        query: dict[str, str | int | float | bool] | None = None,
        headers: dict[str, str] | None = None,
        body: Any = None,
        timeout_s: float = 60.0,
        per_call_cap_usdc: float | None = None,
    ) -> CallApiResult:
        """Make a paid call against a Gatefare-listed API. Raises
        SpendCapError if the cap would be exceeded BEFORE any
        signature is produced."""
        if not self._wallet:
            raise RuntimeError(
                "Gatefare.call_api requires wallet_private_key in the constructor.",
            )

        # Look up the listing for the local price+chain. The cap
        # check must run BEFORE we issue the unauthenticated request
        # because that's the only way to defend against a
        # compromised server quoting an inflated price.
        api = self.get_api(slug)
        if not api:
            raise GatefareApiError(404, "API_NOT_FOUND", f"Unknown slug {slug}", slug)

        self._spend.authorize(api.price_usdc, per_call_cap_usdc)

        # Rebuild the wallet for this listing's chain if needed.
        wallet = (
            self._wallet
            if api.network == self._wallet.network
            else self._rebuild_wallet_for(api.network)
        )

        url = self._build_proxy_url(api.proxy_url, query)
        request_body = self._serialize_body(body)
        extra_headers = dict(headers or {})

        # Step 1: unauthenticated request. Expect 402.
        r = self._http.request(method, url, headers=extra_headers, content=request_body, timeout=timeout_s)
        if r.status_code != 402:
            # Free / public path — no payment needed, just surface the
            # response as zero-cost.
            return self._format_result(r, paid_usdc=0.0, claim_id=None, settle_tx=None)

        try:
            quote = r.json()
        except Exception as exc:
            raise GatefareApiError(402, "MALFORMED_402", "Resource server 402 had no JSON quote", slug) from exc

        accepts = quote.get("accepts") if isinstance(quote, dict) else None
        if not accepts:
            raise GatefareApiError(402, "MALFORMED_402", "402 quote missing 'accepts' array", slug)
        accept = accepts[0]

        # Cross-check the server's quoted price against the catalog
        # price — refuse if they diverge >1%. This catches both
        # malicious quote inflation and accidental price changes
        # between catalog read and the actual settle.
        quoted_usdc = int(accept["maxAmountRequired"]) / 1_000_000
        if quoted_usdc > api.price_usdc * 1.01:
            raise GatefareApiError(
                402, "PRICE_DIVERGENCE",
                f"Server quoted {quoted_usdc} USDC but catalog says {api.price_usdc} — refusing to sign.",
                slug,
            )
        # Re-authorize at the actual quoted price.
        self._spend.authorize(quoted_usdc, per_call_cap_usdc)

        # Step 2: sign EIP-3009.
        signed = sign_eip3009_authorization(
            wallet,
            PaymentRequirements(
                value=accept["maxAmountRequired"],
                pay_to=accept["payTo"],
                network=accept["network"],
                resource=accept["resource"],
            ),
        )

        # Step 3: resend with X-Payment.
        paid_headers = {**extra_headers, "X-Payment": signed.x_payment_header}
        paid = self._http.request(
            method,
            url,
            headers=paid_headers,
            content=request_body,
            timeout=timeout_s,
        )

        if 200 <= paid.status_code < 300:
            self._spend.record(quoted_usdc)
            return self._format_result(
                paid,
                paid_usdc=quoted_usdc,
                claim_id=paid.headers.get("x-gatefare-claim-id"),
                settle_tx=paid.headers.get("x-gatefare-settle-tx"),
            )

        # Retry path — only when server gave us a claim id and the
        # status is retryable.
        claim_id = paid.headers.get("x-gatefare-claim-id")
        settle_tx = paid.headers.get("x-gatefare-settle-tx")
        if claim_id and is_retryable_status(paid.status_code):
            return self._retry_loop(claim_id, quoted_usdc, paid, settle_tx)

        # Non-retryable failure — surface the response, NOT raise.
        return self._format_result(
            paid, paid_usdc=quoted_usdc, claim_id=claim_id, settle_tx=settle_tx,
        )

    def check_balance(self, network: GatefareNetwork | None = None) -> WalletBalance:
        """Read the USDC balance for the configured wallet."""
        if not self._wallet:
            raise RuntimeError("Gatefare.check_balance requires a wallet.")
        target = self._wallet if (not network or network == self._wallet.network) else self._rebuild_wallet_for(network)
        micros, usdc = read_usdc_balance(target, http=self._http)
        return WalletBalance(
            usdc=usdc,
            usdc_micros=micros,
            address=target.address,
            network=target.network,
        )

    @property
    def spend_manager(self) -> SpendCapManager:
        """Expose the spend cap tracker for UI use ("spent $2.10 of $10.00")."""
        return self._spend

    # ── internals ──────────────────────────────────────────────

    def _catalog_ctx(self) -> CatalogContext:
        return CatalogContext(
            base_url=self._base_url,
            http=self._http,
            personal_access_token=self._pat,
        )

    def _build_proxy_url(self, proxy_path: str, query: dict | None) -> str:
        base = proxy_path if proxy_path.startswith("http") else f"{self._base_url}{proxy_path}"
        if not query:
            return base
        from urllib.parse import urlencode

        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{urlencode({k: str(v) for k, v in query.items()})}"

    def _serialize_body(self, body: Any) -> bytes | None:
        if body is None:
            return None
        if isinstance(body, (bytes, bytearray)):
            return bytes(body)
        if isinstance(body, str):
            return body.encode("utf-8")
        return json.dumps(body).encode("utf-8")

    def _format_result(
        self,
        r: httpx.Response,
        *,
        paid_usdc: float,
        claim_id: str | None,
        settle_tx: str | None,
    ) -> CallApiResult:
        headers = {k.lower(): v for k, v in r.headers.items()}
        data: Any
        ct = headers.get("content-type", "").lower()
        if "application/json" in ct or "+json" in ct:
            try:
                data = r.json()
            except Exception:
                data = r.text
        elif ct.startswith("text/"):
            data = r.text
        else:
            data = r.content
        return CallApiResult(
            status=r.status_code,
            headers=headers,
            data=data,
            paid_usdc=paid_usdc,
            claim_id=claim_id,
            settle_tx_hash=settle_tx,
        )

    def _rebuild_wallet_for(self, network: GatefareNetwork) -> WalletState:
        if not self._wallet_raw_key:
            raise RuntimeError("rebuild_wallet_for called without an initial wallet")
        return create_wallet_state(self._wallet_raw_key, network)

    def _retry_loop(
        self,
        claim_id: str,
        quoted_usdc: float,
        paid: httpx.Response,
        settle_tx: str | None,
    ) -> CallApiResult:
        last_status = paid.status_code
        last_headers = {k.lower(): v for k, v in paid.headers.items()}
        last_body = paid.content
        last_ct = last_headers.get("content-type", "application/octet-stream")

        ctx = ClaimContext(base_url=self._base_url, http=self._http)
        for attempt in range(1, DEFAULT_RETRY_BUDGET + 1):
            time.sleep(backoff_seconds(attempt))
            try:
                r = retry_claim(ctx, claim_id)
                if 200 <= r.status < 300:
                    self._spend.record(quoted_usdc)
                    return CallApiResult(
                        status=r.status,
                        headers=r.headers,
                        data=self._decode_body(r.body, r.content_type),
                        paid_usdc=quoted_usdc,
                        claim_id=claim_id,
                        settle_tx_hash=settle_tx,
                    )
                last_status = r.status
                last_headers = r.headers
                last_body = r.body
                last_ct = r.content_type
                if not is_retryable_status(r.status):
                    break
            except Exception:
                if attempt == DEFAULT_RETRY_BUDGET:
                    raise

        return CallApiResult(
            status=last_status,
            headers=last_headers,
            data=self._decode_body(last_body, last_ct),
            paid_usdc=quoted_usdc,
            claim_id=claim_id,
            settle_tx_hash=settle_tx,
        )

    def _decode_body(self, buf: bytes, content_type: str) -> Any:
        ct = content_type.lower()
        if "application/json" in ct or "+json" in ct:
            try:
                return json.loads(buf.decode("utf-8"))
            except Exception:
                return buf.decode("utf-8", errors="replace")
        if ct.startswith("text/"):
            return buf.decode("utf-8", errors="replace")
        return buf
