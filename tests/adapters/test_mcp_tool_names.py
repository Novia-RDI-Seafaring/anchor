"""MCP tool-name compatibility checks."""
from __future__ import annotations

import re

from anchor.adapters.mcp import handlers_canvas
from anchor.extensions.anchor_cad import mcp_handlers as cad_handlers
from anchor.extensions.anchor_fmus import mcp_handlers as fmu_handlers
from anchor.extensions.anchor_pdfs import mcp_handlers as pdf_handlers
from anchor.extensions.anchor_sysml import mcp_handlers as sysml_handlers


def test_all_exported_mcp_tool_names_are_client_safe():
    definitions = [
        *handlers_canvas.tool_definitions(),
        *pdf_handlers.tool_definitions(),
        *fmu_handlers.tool_definitions(),
        *cad_handlers.TOOL_DEFINITIONS,
        *sysml_handlers.tool_definitions(),
    ]

    pattern = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    bad_names = [definition["name"] for definition in definitions if not pattern.fullmatch(definition["name"])]

    assert bad_names == []
