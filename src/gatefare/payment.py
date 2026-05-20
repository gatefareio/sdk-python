"""EIP-3009 transferWithAuthorization signing + X-Payment header.

Pure module — no network I/O. Mirrors the TypeScript SDK's `payment.ts`
so the same fixtures produce the same signatures cross-language.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from eth_account.messages import encode_typed_data

from .types import GatefareNetwork
from .wallet import WalletState

# Per-network USDC contract metadata used to build the EIP-712 domain.
# Both Base mainnet + Sepolia USDC use the same name/version/decimals;
# we still parametrize so future chains stay correct.
_USDC_BY_NETWORK: dict[str, dict[str, Any]] = {
    "eip155:8453": {
        "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "name": "USD Coin",
        "version": "2",
        "chain_id": 8453,
    },
    "eip155:84532": {
        "address": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "name": "USDC",
        "version": "2",
        "chain_id": 84532,
    },
}


@dataclass
class PaymentRequirements:
    """Inputs the resource server tells us about (parsed from the 402
    challenge body)."""

    value: str  # USDC amount in atomic micros, decimal string
    pay_to: str  # split contract address
    network: GatefareNetwork
    resource: str


@dataclass
class SignedAuthorization:
    """Result of signing — what we attach to the resending request."""

    x_payment_header: str
    value_micros: int
    nonce_hex: str
    valid_before_sec: int


def _random_nonce_hex() -> str:
    """32-byte cryptographically-random nonce, 0x-prefixed."""
    return "0x" + secrets.token_hex(32)


def sign_eip3009_authorization(
    wallet: WalletState,
    req: PaymentRequirements,
    now: float | None = None,
) -> SignedAuthorization:
    """Sign an EIP-3009 transferWithAuthorization and return the
    X-Payment header payload (base64-encoded x402 v2 JSON).

    Validity window: 5 minutes from issuance. Long enough to cover
    facilitator round-trip; short enough that a stolen authorization
    expires before an attacker can exploit it at scale.
    """
    usdc = _USDC_BY_NETWORK.get(req.network)
    if not usdc:
        raise ValueError(f"No USDC contract known for {req.network}")

    now_s = int(now if now is not None else time.time())
    valid_after = 0
    valid_before = now_s + 300  # 5 minutes
    nonce = _random_nonce_hex()
    value_micros = int(req.value)

    domain = {
        "name": usdc["name"],
        "version": usdc["version"],
        "chainId": usdc["chain_id"],
        "verifyingContract": usdc["address"],
    }
    types = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ],
    }
    message = {
        "from": wallet.account.address,
        "to": req.pay_to,
        "value": value_micros,
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": nonce,
    }

    full_message = {
        "types": types,
        "primaryType": "TransferWithAuthorization",
        "domain": domain,
        "message": message,
    }
    encoded = encode_typed_data(full_message=full_message)
    signed = wallet.account.sign_message(encoded)
    signature_hex = signed.signature.hex()
    if not signature_hex.startswith("0x"):
        signature_hex = "0x" + signature_hex

    payload = {
        "x402Version": 2,
        "scheme": "exact",
        "network": req.network,
        "payload": {
            "signature": signature_hex,
            "authorization": {
                "from": wallet.account.address,
                "to": req.pay_to,
                "value": str(value_micros),
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": nonce,
            },
        },
    }
    raw = json.dumps(payload, separators=(",", ":"))
    x_payment_header = base64.b64encode(raw.encode("utf-8")).decode("ascii")

    return SignedAuthorization(
        x_payment_header=x_payment_header,
        value_micros=value_micros,
        nonce_hex=nonce,
        valid_before_sec=valid_before,
    )


def usdc_to_micros(amount: str | float | int) -> int:
    """Convert decimal USDC to 6-decimal atomic units. Same semantics
    as `parseUnits(amount, 6)` in viem.

    Examples:
        usdc_to_micros(1)       # → 1_000_000
        usdc_to_micros("0.01")  # → 10_000
        usdc_to_micros("0.000001")  # → 1
    """
    s = f"{amount:.6f}" if isinstance(amount, (int, float)) else str(amount)
    if "." not in s:
        return int(s) * 1_000_000
    whole, frac = s.split(".", 1)
    # Pad/truncate fractional to exactly 6 digits, then concat.
    frac = (frac + "000000")[:6]
    return int(whole) * 1_000_000 + int(frac)
