"""OpenAI function-calling adapter.

Produces tool descriptors in the exact shape openai-python expects.

Usage:

    from openai import OpenAI
    from gatefare import Gatefare
    from gatefare.adapters.openai_tools import gatefare_openai_tools, gatefare_openai_dispatch

    gf = Gatefare(wallet_private_key=...)
    tools = gatefare_openai_tools(gf, price_limit_usdc=0.05)

    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "What's the weather in Berlin?"}],
        tools=tools,
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    result = gatefare_openai_dispatch(gf, tool_call)
    # Feed `result` back as a tool-role message and re-call the model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..client import Gatefare


def _fn_name(slug: str) -> str:
    return "gatefare_" + re.sub(r"[^a-zA-Z0-9_]", "_", slug)[:50]


def gatefare_openai_tools(gf: Gatefare, **catalog_kwargs: Any) -> list[dict[str, Any]]:
    """One OpenAI tool descriptor per matching catalog API."""
    apis = gf.list_catalog(**catalog_kwargs)
    return [
        {
            "type": "function",
            "function": {
                "name": _fn_name(api.slug),
                "description": f"{api.name}: {api.description} (price: {api.price}, network: {api.network_name})",
                "parameters": {
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
            },
        }
        for api in apis
    ]


def gatefare_openai_dispatch(gf: Gatefare, tool_call: Any) -> str:
    """Dispatch an OpenAI tool_call back to the SDK. Accepts either
    the official `ChatCompletionMessageToolCall` object or a plain
    dict with the same shape — useful for tests + custom flows."""
    # Normalize accessor for object/dict tool_call.
    if isinstance(tool_call, dict):
        fn = tool_call.get("function") or {}
        name = fn.get("name", "")
        args_str = fn.get("arguments", "{}")
    else:
        name = tool_call.function.name
        args_str = tool_call.function.arguments

    if not name.startswith("gatefare_"):
        return f"Tool {name} is not a Gatefare tool."

    candidate = name[len("gatefare_"):].replace("_", "-")
    api = gf.get_api(candidate)
    if not api:
        return f"No Gatefare listing for {candidate}"

    try:
        args = json.loads(args_str)
    except Exception:
        args = {}

    result = gf.call_api(api.slug, query=args.get("query"))
    if 200 <= result.status < 300:
        return result.data if isinstance(result.data, str) else json.dumps(result.data)
    return f"Upstream returned HTTP {result.status}: {json.dumps(result.data)[:500]}"
