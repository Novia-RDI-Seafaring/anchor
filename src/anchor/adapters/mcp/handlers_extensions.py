"""MCP surface for bundled extension runtime diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping

from anchor.adapters.extension_host import (
    ExtensionRuntimeStatus,
    extension_runtime_status_payload,
)

TOOL_NAME = "anchor_extension_status"

TOOL_DEFINITION = {
    "name": TOOL_NAME,
    "description": (
        "Report whether each bundled extension runtime started successfully, "
        "including unavailable reasons and error types."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


def call_tool(statuses: Mapping[str, ExtensionRuntimeStatus]) -> str:
    """Serialize the shared extension diagnostic payload for MCP."""
    return json.dumps(extension_runtime_status_payload(statuses))
