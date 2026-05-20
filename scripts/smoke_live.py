"""Live smoke test against gatefare.io.

Read-only — does not make paid calls. Verifies that:
  1. list_catalog returns the expected shape
  2. get_api handles both 200 and 404
  3. All four adapters produce valid descriptors
  4. SpendCapError fires (and the wallet does NOT sign) when the cap
     would be exceeded

Run with:
    python scripts/smoke_live.py
"""

import sys

from gatefare import Gatefare, GatefareApiError, SpendCapError
from gatefare.adapters.anthropic_tools import gatefare_anthropic_tools
from gatefare.adapters.langchain import (
    gatefare_catalog_tools,
    gatefare_langchain_tool,
)
from gatefare.adapters.llamaindex import gatefare_llamaindex_tool
from gatefare.adapters.openai_tools import gatefare_openai_tools

# Pinned well-known throwaway key from Web3 docs (safe to publish).
TEST_KEY = "0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
failures = 0


def ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}✓{RESET} {label}{f' {DIM}— {detail}{RESET}' if detail else ''}")


def fail(label: str, err: object) -> None:
    global failures
    failures += 1
    print(f"  {RED}✗{RESET} {label}\n      {RED}{err}{RESET}")


def smoke() -> int:
    print("\n[smoke] gatefare (python) vs https://gatefare.io (read-only)\n")

    with Gatefare(base_url="https://gatefare.io") as gf:
        # ── 1. list_catalog ────────────────────────────────────
        print("list_catalog")
        try:
            apis = gf.list_catalog(limit=5)
            if not isinstance(apis, list):
                raise AssertionError("not a list")
            if not apis:
                raise AssertionError("empty (expected at least 1 live listing)")
            if len(apis) > 5:
                raise AssertionError(f"limit ignored: got {len(apis)}")
            ok("returned non-empty list", f"{len(apis)} apis")
        except Exception as err:
            fail("list_catalog basic", err)
            return 1

        first = apis[0]
        try:
            for k in ("slug", "name", "price", "price_usdc", "network", "proxy_url"):
                if getattr(first, k, None) in (None, ""):
                    raise AssertionError(f'field "{k}" missing on sample API')
            ok("required fields present")
        except Exception as err:
            fail("list_catalog shape", err)

        try:
            if not isinstance(first.price_usdc, (int, float)) or first.price_usdc < 0:
                raise AssertionError(f"price_usdc = {first.price_usdc}")
            ok("price_usdc is finite non-negative", str(first.price_usdc))
        except Exception as err:
            fail("price_usdc parsing", err)

        # ── 2. price filter ────────────────────────────────────
        try:
            cheap = gf.list_catalog(price_limit_usdc=0.10, limit=20)
            for a in cheap:
                if a.price_usdc > 0.10:
                    raise AssertionError(f"{a.slug} costs {a.price_usdc}")
            ok("price_limit_usdc respected", f"{len(cheap)} apis under $0.10")
        except Exception as err:
            fail("list_catalog price filter", err)

        # ── 3. get_api roundtrip ────────────────────────────────
        print("\nget_api")
        try:
            api = gf.get_api(first.slug)
            if not api or api.slug != first.slug:
                raise AssertionError("roundtrip mismatch")
            ok("happy path roundtrip", api.name)
        except Exception as err:
            fail("get_api", err)

        try:
            missing = gf.get_api("__definitely-not-a-real-slug-xyz__")
            if missing is not None:
                raise AssertionError(f"expected None, got {missing}")
            ok("404 returns None")
        except Exception as err:
            fail("get_api 404 behaviour", err)

        # ── 4. adapters ────────────────────────────────────────
        print("\nadapters")
        try:
            d = gatefare_langchain_tool(gf, slug=first.slug)
            if not d["name"] or not d["description"] or not callable(d["func"]):
                raise AssertionError(f"bad descriptor: {d}")
            ok("langchain single tool", d["name"])
        except Exception as err:
            fail("langchain adapter", err)

        try:
            tools = gatefare_catalog_tools(gf, limit=3)
            if not tools:
                raise AssertionError("empty toolbelt")
            ok("langchain catalog tools", f"{len(tools)} tools")
        except Exception as err:
            fail("langchain catalog adapter", err)

        try:
            tools = gatefare_openai_tools(gf, limit=2)
            for t in tools:
                if t["type"] != "function" or not t["function"]["name"].startswith("gatefare_"):
                    raise AssertionError(f"bad shape: {t}")
            ok("openai tools", f"{len(tools)} tools")
        except Exception as err:
            fail("openai adapter", err)

        try:
            tools = gatefare_anthropic_tools(gf, limit=2)
            for t in tools:
                if not t["name"].startswith("gatefare_") or not t["input_schema"]:
                    raise AssertionError(f"bad shape: {t}")
            ok("anthropic tools", f"{len(tools)} tools")
        except Exception as err:
            fail("anthropic adapter", err)

        try:
            d = gatefare_llamaindex_tool(gf, slug=first.slug)
            if not d["name"] or not callable(d["fn"]):
                raise AssertionError("bad llamaindex shape")
            ok("llamaindex single tool", d["name"])
        except Exception as err:
            fail("llamaindex adapter", err)

    # ── 5. spend cap blocks before signing ─────────────────────
    print("\nspend cap protects wallet")
    try:
        with Gatefare(
            wallet_private_key=TEST_KEY,
            base_url="https://gatefare.io",
            spend_caps={"per_call_usdc": 0.0001},
        ) as gf:
            apis = gf.list_catalog(limit=1)
            if not apis:
                ok("skipped (no catalog listings)")
            else:
                try:
                    gf.call_api(apis[0].slug)
                    raise AssertionError("expected SpendCapError but call succeeded")
                except SpendCapError as err:
                    ok("SpendCapError thrown", err.reason)
                except GatefareApiError as err:
                    ok("blocked before signing (GatefareApiError)", err.code or str(err.status))
    except Exception as err:
        fail("spend cap protection", err)

    print()
    if failures == 0:
        print(f"{GREEN}[smoke] all checks passed{RESET}\n")
        return 0
    print(f"{RED}[smoke] {failures} check(s) failed{RESET}\n")
    return 1


if __name__ == "__main__":
    sys.exit(smoke())
