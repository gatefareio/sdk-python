"""LlamaIndex Python adapter.

Returns descriptors compatible with `llama_index.core.tools.FunctionTool`.

Usage:

    from llama_index.core.tools import FunctionTool
    from gatefare.adapters.llamaindex import gatefare_llamaindex_tool

    d = gatefare_llamaindex_tool(gf, slug="weather-now")
    tool = FunctionTool.from_defaults(fn=d["fn"], name=d["name"], description=d["description"])
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, TypedDict

from ..client import Gatefare


class LlamaIndexToolDescriptor(TypedDict):
    name: str
    description: str
    fn: Callable[..., str]


def _sanitize(s: str) -> str:
    return "gatefare_" + re.sub(r"[^a-zA-Z0-9_]", "_", s)[:50]


def gatefare_llamaindex_tool(
    gf: Gatefare, *, slug: str, name: str | None = None, description: str | None = None,
) -> LlamaIndexToolDescriptor:
    api = gf.get_api(slug)
    if not api:
        raise ValueError(f'Gatefare: unknown slug "{slug}"')

    tool_name = name or _sanitize(api.slug)
    tool_desc = description or f"{api.name}: {api.description} ({api.price})"

    def fn(query: dict[str, Any] | None = None) -> str:
        result = gf.call_api(slug, query=query)
        if 200 <= result.status < 300:
            return result.data if isinstance(result.data, str) else json.dumps(result.data)
        return f"Upstream returned HTTP {result.status}: {json.dumps(result.data)[:500]}"

    return {"name": tool_name, "description": tool_desc, "fn": fn}


def gatefare_llamaindex_catalog_tools(
    gf: Gatefare, **catalog_kwargs: Any,
) -> list[LlamaIndexToolDescriptor]:
    apis = gf.list_catalog(**catalog_kwargs)
    return [gatefare_llamaindex_tool(gf, slug=a.slug) for a in apis]
