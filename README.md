# gatefare

Python client for the [Gatefare](https://gatefare.io) x402 payment
marketplace. Pay any Gatefare-listed API in USDC on Base with a few
lines of code. Non-custodial. No platform account required for paying;
your wallet signs every authorization.

## Install

```bash
pip install gatefare
```

Requires Python 3.10+.

## Quick start

```python
from gatefare import Gatefare

gf = Gatefare(
    wallet_private_key=os.environ["WALLET_PRIVATE_KEY"],
    spend_caps={"per_call_usdc": 0.50, "per_day_usdc": 5.00},
)

# Search the catalog
apis = gf.list_catalog(price_limit_usdc=0.10, limit=5)

# Pay and call
result = gf.call_api(apis[0].slug, query={"city": "Berlin"})
print(result.status, result.data)   # 200 { ... }

# Check balance
balance = gf.check_balance()
print(balance.usdc)   # 12.345
```

## What the SDK does for you

- Speaks the x402 v2 protocol: handles the 402 challenge, signs an
  EIP-3009 USDC `transferWithAuthorization` with your wallet, resends
  with the `X-Payment` header, decodes the response.
- Enforces SDK-local spend caps **before** signing any authorization
  so a compromised resource server cannot drain the wallet past
  whatever you configured.
- Cross-checks the server's quoted price against the catalog listing
  and refuses to sign if they diverge by more than 1%.
- Retries failed claims automatically through Gatefare's 24h /
  10-attempt budget via the `/p/_claim/<id>` endpoint.
- Decodes JSON / text responses without you having to handle the raw
  stream.

## What the SDK does NOT do

- Custody your funds. The private key never leaves your process; we
  do not run a hosted wallet. Pass `wallet_private_key` from an env
  var, KMS, or hardware signer (whatever returns the `0x...` hex).
- Charge you for failed settles. If the on-chain settle reverts, no
  spend is recorded against your daily cap.
- Connect to the chain for catalog reads. Catalog endpoints are pure
  HTTP and work without a wallet — useful for read-only discovery.

## Spend caps

Two layers of guardrail. Both are enforced locally, before any wire
activity that costs money:

```python
gf = Gatefare(
    wallet_private_key=...,
    spend_caps={
        "per_call_usdc": 1.00,   # default 1.00
        "per_day_usdc": 10.00,   # default 10.00
    },
)
```

Per-call cap can be overridden per call:

```python
gf.call_api("expensive-listing", per_call_cap_usdc=5.00)
```

Per-day cap resets at midnight UTC. Backed by an in-process dict;
provide a custom `SpendStorage` (any class with `read(day_key)` and
`add(day_key, delta)`) to make it crash-safe across restarts.

## Framework adapters

All optional. Each subpackage exposes plain dicts that match the
host framework's expected shape — we do not import any framework as
a runtime dependency.

### LangChain

```python
from langchain.tools import Tool
from gatefare.adapters.langchain import (
    gatefare_langchain_tool, gatefare_catalog_tools,
)

# One specific Gatefare API as a tool
d = gatefare_langchain_tool(gf, slug="weather-now")
tool = Tool(name=d["name"], description=d["description"], func=d["func"])

# Or expose the whole filtered catalog as a toolbelt
descs = gatefare_catalog_tools(gf, price_limit_usdc=0.10)
tools = [Tool(name=d["name"], description=d["description"], func=d["func"]) for d in descs]
```

### LlamaIndex

```python
from llama_index.core.tools import FunctionTool
from gatefare.adapters.llamaindex import gatefare_llamaindex_tool

d = gatefare_llamaindex_tool(gf, slug="weather-now")
tool = FunctionTool.from_defaults(fn=d["fn"], name=d["name"], description=d["description"])
```

### OpenAI function-calling

```python
from openai import OpenAI
from gatefare.adapters.openai_tools import gatefare_openai_tools, gatefare_openai_dispatch

client = OpenAI()
tools = gatefare_openai_tools(gf, price_limit_usdc=0.05)

resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What's the weather in Berlin?"}],
    tools=tools,
)

tool_call = resp.choices[0].message.tool_calls[0]
result = gatefare_openai_dispatch(gf, tool_call)
# Feed `result` back as a tool-role message and re-call the model.
```

### Anthropic tool-use

```python
import anthropic
from gatefare.adapters.anthropic_tools import gatefare_anthropic_tools, gatefare_anthropic_dispatch

client = anthropic.Anthropic()
tools = gatefare_anthropic_tools(gf, price_limit_usdc=0.05)

message = client.messages.create(
    model="claude-3-5-sonnet-latest",
    max_tokens=1024,
    messages=[{"role": "user", "content": "What's the weather in Berlin?"}],
    tools=tools,
)
for block in message.content:
    if block.type == "tool_use":
        result = gatefare_anthropic_dispatch(gf, block)
```

## Errors

Two named exceptions:

- `SpendCapError` — your call was refused locally because it would
  exceed a configured spend cap. The wallet never produced a signature.
- `GatefareApiError` — Gatefare returned a non-2xx response that the
  SDK cannot recover from (unknown slug, exhausted claim, malformed
  quote).

Non-2xx responses from the upstream API (404 from a paid endpoint,
500 after a successful settle that exhausted retries) are surfaced
as the `status` field on `CallApiResult` rather than raised.

## Configuration reference

```python
gf = Gatefare(
    wallet_private_key=...,             # required for paid calls
    base_url="https://gatefare.io",     # override for staging
    spend_caps={"per_call_usdc": 1.0, "per_day_usdc": 10.0},
    personal_access_token="gfpat_...",  # optional, raises rate limits
    http=httpx.Client(timeout=30),      # optional, for tests / custom timeouts
)
```

Use `with Gatefare(...) as gf:` to auto-close the underlying httpx
client when done.

## License

MIT. See [LICENSE](./LICENSE).

## Links

- Gatefare website: https://gatefare.io
- Catalog: https://gatefare.io/catalog
- Issues: https://github.com/gatefareio/sdk-python/issues
- Source: https://github.com/gatefareio/sdk-python
- TypeScript SDK: https://github.com/gatefareio/sdk-typescript
