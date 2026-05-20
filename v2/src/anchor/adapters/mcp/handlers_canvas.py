"""MCP tool definitions backed by WorkspaceService.

Tool names keep the v1 `canvas_*` prefix so existing agent prompts continue
to work; every tool now takes `workspace_slug` as its first arg.
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError


# ── Byte-fetch envelope ─────────────────────────────────────────────────────
#
# Mirrors the contract used by anchor_pdfs.mcp_handlers._byte_envelope.
# Duplicated rather than imported because adapters/mcp/handlers_canvas
# is in core-adjacent code that shouldn't depend on an extension. The
# contract is *the* shared piece — keep these two implementations in sync.
def _byte_envelope_from_result(*, path: Path | None, bytes_: bytes | None, content_type: str, fmt: str) -> str:
    if fmt == "path":
        if path is None:
            return json.dumps({"error": "snapshot returned inline bytes; request format='base64'"})
        return json.dumps({
            "format": "path", "value": str(path), "content_type": content_type,
            "size_bytes": path.stat().st_size if path.exists() else None,
        })
    if fmt == "base64":
        raw = bytes_ if bytes_ is not None else (path.read_bytes() if path else b"")
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": content_type,
            "size_bytes": len(raw),
        })
    if fmt == "inline":
        # Hand the raw bytes back via the special _mcp_image_b64 marker so
        # the MCP server wrapper can promote the result to an MCP
        # ImageContent block and have the host harness display it inline.
        # SVG is not an image content type in MCP today; emit it as text.
        raw = bytes_ if bytes_ is not None else (path.read_bytes() if path else b"")
        if content_type.startswith("image/") and content_type != "image/svg+xml":
            return json.dumps({
                "_mcp_image_b64": base64.b64encode(raw).decode("ascii"),
                "_mcp_mime": content_type,
            })
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": content_type,
            "size_bytes": len(raw),
        })
    return json.dumps({"error": f"unknown format: {fmt!r} (use 'path', 'base64', or 'inline')"})


def _ctype_for(name: str) -> str:
    guess, _ = mimetypes.guess_type(name)
    return guess or "application/octet-stream"


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "canvas_get_state",
            "description": "Return the full canvas state (version, nodes, edges, metadata).",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_add_node",
            "description": "Add a node by node_type, label, x, y, parent, data.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "node_type": {"type": "string"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "parent": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_update_node",
            "description": "Patch a node's fields.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_remove_node",
            "description": "Delete a node by id (cascades connected edges).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_add_edge",
            "description": "Connect two nodes (source, target, label, edge_type, data).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "label": {"type": "string"},
                    "edge_type": {"type": "string", "enum": ["floating", "anchored"]},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug", "source", "target"],
            },
        },
        {
            "name": "canvas_remove_edge",
            "description": "Delete an edge by id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_clear",
            "description": "Wipe the canvas (cards + edges).",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_create_workspace",
            "description": "Create a new workspace folder.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "canvas_list_workspaces",
            "description": "List all workspaces.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "canvas_organize_subtree",
            "description": (
                "Re-lay-out the subtree under root_id into a tidy tree. Emits one "
                "NodeMoved per descendant whose position changes; the root stays put. "
                "orientation = 'vertical' (default) or 'horizontal'."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "root_id": {"type": "string"},
                    "orientation": {
                        "type": "string",
                        "enum": ["vertical", "horizontal"],
                        "default": "vertical",
                    },
                    "algo": {
                        "type": "string",
                        "enum": ["dagre"],
                        "default": "dagre",
                    },
                },
                "required": ["workspace_slug", "root_id"],
            },
        },
        {
            "name": "canvas_snapshot",
            "description": (
                "Render a workspace canvas to PNG and return the bytes "
                "(as a path or base64). Use format='base64' from off-machine "
                "agents; same envelope as get_page_image / get_crop."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["path", "base64", "inline"],
                        "default": "inline",
                        "description": "'inline' renders the snapshot as an MCP ImageContent block so the host harness (Claude Code, Cursor, ...) displays it inline. 'path' returns the file path; 'base64' returns raw base64 inside the JSON envelope.",
                    },
                    "image_format": {"type": "string", "enum": ["png", "svg"], "default": "png"},
                    "viewport": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "[width, height] in CSS pixels.",
                    },
                    "full_page": {"type": "boolean", "default": True},
                },
                "required": ["workspace_slug"],
            },
        },
    ]


async def call_tool(svc: WorkspaceService, name: str, args: dict[str, Any]) -> str:
    try:
        if name == "canvas_get_state":
            return json.dumps(await svc.get_state(args["workspace_slug"]))
        if name == "canvas_create_workspace":
            return json.dumps(await svc.create_workspace(args["slug"], title=args.get("title", "")))
        if name == "canvas_list_workspaces":
            return json.dumps(await svc.list_workspaces())
        if name == "canvas_add_node":
            slug = args.pop("workspace_slug")
            state, env = await svc.add_node(slug, **args)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_update_node":
            slug = args.pop("workspace_slug")
            node_id = args.pop("id")
            fields = {k: v for k, v in args.items() if v is not None}
            if {"x", "y"} <= fields.keys() and len(fields) == 2:
                state, env = await svc.move_node(slug, node_id, fields["x"], fields["y"])
            else:
                state, env = await svc.update_node(slug, node_id, fields)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_remove_node":
            state, envelopes = await svc.remove_node(args["workspace_slug"], args["id"])
            return json.dumps({"events": [e.model_dump() for e in envelopes], "state": state.get_state()})
        if name == "canvas_add_edge":
            slug = args.pop("workspace_slug")
            state, env = await svc.add_edge(slug, **args)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_remove_edge":
            state, env = await svc.remove_edge(args["workspace_slug"], args["id"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_clear":
            state, env = await svc.clear(args["workspace_slug"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_organize_subtree":
            try:
                state, envelopes = await svc.organize_subtree(
                    args["workspace_slug"], args["root_id"],
                    orientation=args.get("orientation", "vertical"),
                    algo=args.get("algo", "dagre"),
                )
            except ValueError as e:
                return json.dumps({"error": str(e)})
            moves = [
                {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
                for env in envelopes
            ]
            return json.dumps({
                "moves": moves,
                "event_count": len(envelopes),
                "state": state.get_state(),
            })
        if name == "canvas_snapshot":
            envelope_fmt = args.get("format", "path")
            image_fmt = args.get("image_format", "png")
            viewport = args.get("viewport")
            if viewport is not None:
                viewport = (int(viewport[0]), int(viewport[1]))
            full_page = bool(args.get("full_page", True))
            try:
                result = await svc.snapshot(
                    args["workspace_slug"],
                    format=image_fmt,
                    viewport=viewport,
                    full_page=full_page,
                )
            except RuntimeError as e:
                return json.dumps({"error": str(e)})
            except ValueError as e:
                return json.dumps({"error": str(e)})
            except NotImplementedError as e:
                return json.dumps({"error": str(e)})
            return _byte_envelope_from_result(
                path=result.path, bytes_=result.bytes_,
                content_type=result.content_type, fmt=envelope_fmt,
            )
    except CommandError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool: {name}"})
