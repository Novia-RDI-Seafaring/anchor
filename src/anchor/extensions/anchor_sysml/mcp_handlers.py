"""MCP tools exposed by anchor-sysml.

Tool names use underscores because Claude Desktop rejects dots in MCP tool
names. Dotted names are still accepted as legacy aliases by ``call_tool``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_sysml.core.services import SysmlService

LEGACY_TOOL_ALIASES = {
    "sysml.render": "sysml_render",
    "sysml.export": "sysml_export",
}


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "sysml_render",
            "description": (
                "Parse a SysML v2 textual document and place its packages, "
                "blocks (part def / part), and requirements onto the canvas. "
                "Supply either inline `text` or a `path` to a .sysml file."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "text": {"type": "string"},
                    "path": {"type": "string"},
                    "x_offset": {"type": "number", "default": 0},
                    "y_offset": {"type": "number", "default": 0},
                    "filename": {"type": "string"},
                },
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "sysml_export",
            "description": (
                "Reconstruct SysML v2 text from the workspace's sysml:* nodes. "
                "Phase 1 returns a stub header; faithful round-trip lands "
                "with a real renderer."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                },
                "required": ["workspace_slug"],
            },
        },
    ]


async def call_tool(svc: SysmlService, name: str, args: dict[str, Any]) -> str:
    name = LEGACY_TOOL_ALIASES.get(name, name)
    try:
        if name == "sysml_render":
            text = args.get("text")
            if text is None and args.get("path"):
                p = Path(args["path"])
                if not p.exists():
                    return json.dumps({"error": f"path not found: {p}"})
                text = p.read_text()
            if text is None:
                return json.dumps({"error": "either 'text' or 'path' is required"})
            result = await svc.render(
                workspace_slug=args["workspace_slug"],
                text=text,
                x_offset=float(args.get("x_offset", 0)),
                y_offset=float(args.get("y_offset", 0)),
                filename=args.get("filename") or (args.get("path") and Path(args["path"]).name),
            )
            return result.model_dump_json()
        if name == "sysml_export":
            text = await svc.export(workspace_slug=args["workspace_slug"])
            return json.dumps({"text": text})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"error": f"unknown tool: {name}"})


__all__ = ["tool_definitions", "call_tool"]
