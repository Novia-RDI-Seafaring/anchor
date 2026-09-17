"""MCP surface for extension runtime + discovered producer diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from anchor.adapters.extension_host import (
    ExtensionRuntimeStatus,
    extension_status_payload,
)

TOOL_NAME = "anchor_extension_status"

TOOL_DEFINITION = {
    "name": TOOL_NAME,
    "description": (
        "Report whether each bundled extension runtime started successfully, "
        "including unavailable reasons and error types. Also lists discovered "
        "system/project OIP producers with a static PATH check on each "
        "manifest's invocation.command; Anchor never spawns those (the "
        "harness does), so they report started: false."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


def call_tool(
    statuses: Mapping[str, ExtensionRuntimeStatus],
    data_dir: Path | None = None,
) -> str:
    """Serialize the shared extension diagnostic payload for MCP."""
    return json.dumps(extension_status_payload(statuses, data_dir))
