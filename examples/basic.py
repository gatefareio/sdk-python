"""Minimal example — list catalog, make a paid call, check balance.

Run with:
    WALLET_PRIVATE_KEY=0x... python examples/basic.py

Requires a wallet funded with at least the listing price in USDC on
Base mainnet (or Base Sepolia for testnet listings).
"""

import os

from gatefare import Gatefare


def main() -> None:
    with Gatefare(
        wallet_private_key=os.environ["WALLET_PRIVATE_KEY"],
        spend_caps={"per_call_usdc": 0.50, "per_day_usdc": 5.00},
    ) as gf:
        # 1. Search.
        apis = gf.list_catalog(price_limit_usdc=0.10, limit=5)
        print(f"[catalog] {len(apis)} APIs under $0.10")
        for a in apis:
            print(f"  {a.slug:<30} {a.price:>8}  {a.name}")

        if not apis:
            return

        # 2. Balance.
        bal = gf.check_balance()
        print(f"[balance] {bal.usdc} USDC on {bal.network}")
        if bal.usdc < apis[0].price_usdc:
            print("[balance] insufficient — top up the wallet first.")
            return

        # 3. Paid call.
        result = gf.call_api(apis[0].slug)
        print(f"[call] {result.status} — paid {result.paid_usdc} USDC")
        print(f"[call] data: {result.data}")


if __name__ == "__main__":
    main()
