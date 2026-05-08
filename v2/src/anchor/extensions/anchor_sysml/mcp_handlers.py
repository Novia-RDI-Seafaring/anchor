"""MCP tools exposed by anchor-sysml: namespaced ``sysml.*``.

Two tools today: ``sysml.render`` (text → canvas batch) and ``sysml.export``
(canvas state → text — Phase 1 stub). Tool names mirror the FMU/CAD
extensions' style with the ``sysml.`` prefix already baked in.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_sysml.core.services import SysmlService


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "sysml.render",
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
            "name": "sysml.export",
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
    try:
        if name == "sysml.render":
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
        if name == "sysml.export":
            text = await svc.export(workspace_slug=args["workspace_slug"])
            return json.dumps({"text": text})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"error": f"unknown tool: {name}"})


__all__ = ["tool_definitions", "call_tool"]
