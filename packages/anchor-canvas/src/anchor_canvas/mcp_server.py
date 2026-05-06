"""Anchor Canvas MCP Server (stdio entrypoint).

Thin stdio wrapper around the shared handler catalogue from
`mcp_handlers.py`, backed by `HttpOps` against a running anchor-canvas
server. This preserves Claude Code's existing `mcp.json` config:

    {
      "mcpServers": {
        "anchor-canvas": {
          "command": "anchor-canvas-mcp",
          "args": ["--url", "http://localhost:8002"]
        }
      }
    }

For new setups, prefer the in-process MCP at `http://<host>:<port>/mcp/sse`
which the canvas server exposes natively (and which can push live
`resources/updated` notifications when the user interacts with the canvas
in the browser).
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from mcp.server.stdio import stdio_server

from .mcp_handlers import HttpOps, build_server

logger = logging.getLogger(__name__)


async def run(base_url: str) -> None:
    server, _registry = build_server(HttpOps(base_url))
    logger.info("Anchor Canvas MCP (stdio) starting (url=%s)", base_url)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Anchor Canvas MCP (stdio)")
    parser.add_argument("--url", "-u", default="http://localhost:8002", help="Canvas server URL")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()
