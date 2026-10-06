"""Call this process's own Streamable HTTP MCP endpoint."""

from __future__ import annotations

import json
from typing import Any

import httpx2

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def call_tool(url: str, name: str, arguments: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[dict[str, Any], str]:
    async with httpx2.AsyncClient(headers=headers, trust_env=False) as client, streamable_http_client(url, http_client=client) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            protocol = str(initialized.protocol_version)
            result = await session.call_tool(name, arguments)
    if result.is_error:
        detail = _text(result) or "MCP tool returned an error."
        raise RuntimeError(detail)
    if isinstance(result.structured_content, dict):
        return result.structured_content, protocol
    text = _text(result)
    if not text:
        raise RuntimeError(f"Tool {name} returned no content.")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Tool {name} returned {type(parsed).__name__}, expected an object.")
    return parsed, protocol


async def list_tool_names(url: str) -> tuple[list[str], str]:
    async with httpx2.AsyncClient(trust_env=False) as client, streamable_http_client(url, http_client=client) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
    names = [tool.name for tool in listed.tools]
    return names, str(initialized.protocol_version)


def _text(result: Any) -> str:
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            return str(text)
    return ""

