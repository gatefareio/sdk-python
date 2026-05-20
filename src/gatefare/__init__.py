"""
gatefare — Python client for the Gatefare x402 payment marketplace.

Quick start:

    from gatefare import Gatefare

    gf = Gatefare(
        wallet_private_key=os.environ["WALLET_PRIVATE_KEY"],
        spend_caps={"per_call_usdc": 0.50, "per_day_usdc": 5.00},
    )
    apis = gf.list_catalog(price_limit_usdc=0.10, limit=5)
    result = gf.call_api(apis[0].slug, query={"city": "Berlin"})
    balance = gf.check_balance()

Mirrors `@gatefare/client` (TypeScript) — same protocol, same defense
layers, same names where idiomatically possible.
"""

from .client import Gatefare
from .errors import GatefareApiError, SpendCapError
from .spend_cap import DEFAULT_SPEND_CAPS, SpendCapManager
from .types import (
    CallApiResult,
    CatalogApi,
    SpendCaps,
    WalletBalance,
)

__all__ = [
    "Gatefare",
    "GatefareApiError",
    "SpendCapError",
    "SpendCapManager",
    "DEFAULT_SPEND_CAPS",
    "CallApiResult",
    "CatalogApi",
    "SpendCaps",
    "WalletBalance",
]

__version__ = "0.1.0"
