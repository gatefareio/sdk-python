"""Anthropic tool-use adapter.

Produces tool descriptors for the Anthropic Messages API.

Usage:

    import anthropic
    from gatefare import Gatefare
    from gatefare.adapters.anthropic_tools import gatefare_anthropic_tools, gatefare_anthropic_dispatch

    gf = Gatefare(wallet_private_key=...)
    tools = gatefare_anthropic_tools(gf, price_limit_usdc=0.05)

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=1024,
        messages=[{"role": "user", "content": "What's the weather in Berlin?"}],
        tools=tools,
    )
    for block in message.content:
        if block.type == "tool_use":
            result = gatefare_anthropic_dispatch(gf, block)
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..client import Gatefare


def _tool_name(slug: str) -> str:
    # Anthropic tool names match ^[a-zA-Z0-9_-]{1,64}$
    return "gatefare_" + re.sub(r"[^a-zA-Z0-9_-]", "_", slug)[:50]


def gatefare_anthropic_tools(gf: Gatefare, **catalog_kwargs: Any) -> list[dict[str, Any]]:
    apis = gf.list_catalog(**catalog_kwargs)
    return [
        {
            "name": _tool_name(api.slug),
            "description": f"{api.name}: {api.description} (price: {api.price}, network: {api.network_name})",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "object",
                        "description": "Query parameters for the upstream API as key=value pairs.",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": [],
            },
        }
        for api in apis
    ]


def gatefare_anthropic_dispatch(gf: Gatefare, block: Any) -> str:
    """Dispatch an Anthropic tool_use block back to the SDK.
    Accepts either the official `ToolUseBlock` or a dict with `name`
    + `input` fields."""
    if isinstance(block, dict):
        name = block.get("name", "")
        input_data = block.get("input") or {}
    else:
        name = block.name
        input_data = getattr(block, "input", None) or {}

    if not name.startswith("gatefare_"):
        return f"Tool {name} is not a Gatefare tool."

    candidate = name[len("gatefare_"):].replace("_", "-")
    api = gf.get_api(candidate)
    if not api:
        return f"No Gatefare listing for {candidate}"

    query = input_data.get("query") if isinstance(input_data, dict) else None
    result = gf.call_api(api.slug, query=query)
    if 200 <= result.status < 300:
        return result.data if isinstance(result.data, str) else json.dumps(result.data)
    return f"Upstream returned HTTP {result.status}: {json.dumps(result.data)[:500]}"
