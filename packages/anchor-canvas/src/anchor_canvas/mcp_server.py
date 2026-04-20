"""Anchor Canvas MCP Server — expose canvas operations as tools for AI agents.

Connects to a running anchor-canvas server via HTTP.

Start with:
    anchor-canvas-mcp --url http://localhost:8002

Or add to Claude Code's MCP config:
    {
      "mcpServers": {
        "anchor-canvas": {
          "command": "anchor-canvas-mcp",
          "args": ["--url", "http://localhost:8002"]
        }
      }
    }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

_base_url: str = "http://localhost:8002"

app = Server("anchor-canvas")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="canvas_add_node",
            description="Add a node to the canvas. Types: concept, entity, fact, document, spec, image, area, model, plot. "
                        "Returns the created node with its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_type": {"type": "string", "description": "Node type (concept, entity, fact, document, spec, image, area, model, plot)", "default": "concept"},
                    "label": {"type": "string", "description": "Display label for the node"},
                    "x": {"type": "number", "description": "X position", "default": 0},
                    "y": {"type": "number", "description": "Y position", "default": 0},
                    "parent": {"type": "string", "description": "Parent node ID (for nesting inside area nodes)"},
                    "data": {"type": "object", "description": "Additional data (e.g. image_url, properties, markdown)"},
                },
                "required": ["label"],
            },
        ),
        Tool(
            name="canvas_update_node",
            description="Update an existing node's properties (label, position, data).",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node ID to update"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "data": {"type": "object"},
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="canvas_remove_node",
            description="Remove a node and its connected edges from the canvas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node ID to remove"},
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="canvas_add_edge",
            description="Connect two nodes with an edge.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source node ID"},
                    "target": {"type": "string", "description": "Target node ID"},
                    "label": {"type": "string", "description": "Edge label", "default": ""},
                },
                "required": ["source", "target"],
            },
        ),
        Tool(
            name="canvas_remove_edge",
            description="Remove an edge from the canvas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Edge ID to remove"},
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="canvas_get_state",
            description="Get the full current canvas state — all nodes, edges, and metadata.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="canvas_clear",
            description="Clear the entire canvas (remove all nodes and edges).",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _handle_tool(name, arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _handle_tool(name: str, args: dict) -> str:
    async with httpx.AsyncClient(base_url=_base_url, timeout=10) as client:
        if name == "canvas_add_node":
            r = await client.post("/api/nodes", json=args)
        elif name == "canvas_update_node":
            node_id = args.pop("id")
            r = await client.patch(f"/api/nodes/{node_id}", json=args)
        elif name == "canvas_remove_node":
            r = await client.delete(f"/api/nodes/{args['id']}")
        elif name == "canvas_add_edge":
            r = await client.post("/api/edges", json=args)
        elif name == "canvas_remove_edge":
            r = await client.delete(f"/api/edges/{args['id']}")
        elif name == "canvas_get_state":
            r = await client.get("/api/state")
        elif name == "canvas_clear":
            r = await client.post("/api/clear")
        else:
            return f"Unknown tool: {name}"

        return json.dumps(r.json(), indent=2)


async def run(base_url: str) -> None:
    global _base_url
    _base_url = base_url
    logger.info("Anchor Canvas MCP server starting (url=%s)", _base_url)

    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Anchor Canvas MCP Server")
    parser.add_argument("--url", "-u", default="http://localhost:8002", help="Canvas server URL")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()
