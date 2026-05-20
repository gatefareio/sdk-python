"""LangChain Python adapter.

Returns dicts compatible with `langchain.tools.StructuredTool.from_function`
and `langchain_core.tools.Tool`. We do not import langchain itself —
the consumer pulls their own version.

Usage:

    from langchain.tools import Tool
    from gatefare import Gatefare
    from gatefare.adapters.langchain import gatefare_langchain_tool

    gf = Gatefare(wallet_private_key=...)
    descriptor = gatefare_langchain_tool(gf, slug="weather-now")
    tool = Tool(
        name=descriptor["name"],
        description=descriptor["description"],
        func=descriptor["func"],
    )
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, TypedDict

from ..client import Gatefare


class LangChainToolDescriptor(TypedDict):
    name: str
    description: str
    func: Callable[[str], str]


def _sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", s)[:64]


def gatefare_langchain_tool(
    gf: Gatefare,
    *,
    slug: str,
    name: str | None = None,
    description: str | None = None,
) -> LangChainToolDescriptor:
    """One-tool descriptor bound to a specific catalog slug."""
    api = gf.get_api(slug)
    if not api:
        raise ValueError(f'Gatefare: unknown slug "{slug}"')

    tool_name = name or _sanitize(api.slug)
    tool_desc = description or f"{api.name}. {api.description} (price: {api.price})"

    def func(input_str: str) -> str:
        # Accept a JSON object for structured args, plain string for
        # single-param `q`. Empty input → no query.
        query: dict[str, Any] | None = None
        trimmed = (input_str or "").strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                query = json.loads(trimmed)
            except Exception:
                query = {"q": input_str}
        elif trimmed:
            query = {"q": trimmed}

        result = gf.call_api(slug, query=query)
        if 200 <= result.status < 300:
            return result.data if isinstance(result.data, str) else json.dumps(result.data)
        return f"Gatefare call returned HTTP {result.status}: {json.dumps(result.data)[:500]}"

    return {"name": tool_name, "description": tool_desc, "func": func}


def gatefare_catalog_tools(
    gf: Gatefare, **catalog_kwargs: Any,
) -> list[LangChainToolDescriptor]:
    """Toolbelt — one descriptor per catalog API matching the filter."""
    apis = gf.list_catalog(**catalog_kwargs)
    return [gatefare_langchain_tool(gf, slug=a.slug) for a in apis]
