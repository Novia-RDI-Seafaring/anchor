"""Small MCP stdio producer used by the external gateway integration test."""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

server = Server("anchor-test-external-producer")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="echo",
            description="Echo a value from an isolated test producer.",
            inputSchema={
                "type": "object",
                "properties": {"value": {}},
                "required": ["value"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    if name != "echo":
        raise ValueError(f"unknown test tool: {name}")
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps({"echo": arguments.get("value")}),
            )
        ]
    )


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
