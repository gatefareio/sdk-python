"""Thin wrapper around eth_account for in-process EOA wallets.

Browser-injected wallets and CDP-managed wallets are explicitly out of
scope for v0.1 — this module only handles raw private keys held in
the calling process. The key must be sourced safely (env var, KMS,
hardware signer that hands us the hex). We do NOT validate strength;
that is the caller's responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from eth_account import Account
from eth_account.signers.local import LocalAccount

from .types import GatefareNetwork

# Canonical USDC contract per network (checksummed). USDC is 6-decimal
# on every chain we support.
USDC_BASE_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# Default public RPC endpoints. Override via the wallet constructor if
# you have a paid RPC (Alchemy/QuickNode) — the public ones are fine
# for balance reads but get rate-limited under heavier load.
RPC_URL_BY_NETWORK: dict[str, str] = {
    "eip155:8453":  "https://mainnet.base.org",
    "eip155:84532": "https://sepolia.base.org",
}


def _usdc_address(network: str) -> str:
    if network == "eip155:8453":
        return USDC_BASE_MAINNET
    if network == "eip155:84532":
        return USDC_BASE_SEPOLIA
    raise ValueError(f"No USDC contract known for {network}")


def _chain_id(network: str) -> int:
    if network == "eip155:8453":
        return 8453
    if network == "eip155:84532":
        return 84532
    raise ValueError(f"Unknown network: {network}")


@dataclass
class WalletState:
    """Holds the signing account + per-network RPC info. Re-derive on
    a different network via `with_network`."""

    account: LocalAccount
    network: GatefareNetwork
    rpc_url: str

    @property
    def address(self) -> str:
        return self.account.address

    def with_network(self, network: GatefareNetwork, rpc_url: str | None = None) -> WalletState:
        """Bind the same private key to a different chain."""
        return WalletState(
            account=self.account,
            network=network,
            rpc_url=rpc_url or RPC_URL_BY_NETWORK[network],
        )


def create_wallet_state(
    private_key: str,
    network: GatefareNetwork,
    rpc_url: str | None = None,
) -> WalletState:
    """Build a wallet state from a 0x-prefixed (or not) 32-byte hex key."""
    key = private_key if private_key.startswith("0x") else f"0x{private_key}"
    account: LocalAccount = Account.from_key(key)
    return WalletState(
        account=account,
        network=network,
        rpc_url=rpc_url or RPC_URL_BY_NETWORK[network],
    )


def read_usdc_balance(state: WalletState, http: httpx.Client | None = None) -> tuple[int, float]:
    """Read the USDC balance for the wallet's address via eth_call.

    Returns (micros, usdc_decimal). The atomic-unit micros stay as the
    canonical value; the decimal float is for ergonomics.

    We do NOT pull in `web3.py` — it's a heavy dep with build wheels
    and we only need one eth_call per query. Direct JSON-RPC keeps
    `gatefare` slim.
    """
    # `balanceOf(address)` selector is 0x70a08231
    address_padded = state.account.address.lower().removeprefix("0x").rjust(64, "0")
    data = "0x70a08231" + address_padded

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [
            {"to": _usdc_address(state.network), "data": data},
            "latest",
        ],
    }

    client = http or httpx.Client(timeout=10.0)
    try:
        r = client.post(state.rpc_url, json=payload)
        r.raise_for_status()
        body = r.json()
    finally:
        if http is None:
            client.close()

    if "error" in body:
        raise RuntimeError(f"eth_call balanceOf failed: {body['error']}")

    hex_result = body.get("result", "0x0")
    micros = int(hex_result, 16)
    usdc = micros / 1_000_000
    return micros, usdc
