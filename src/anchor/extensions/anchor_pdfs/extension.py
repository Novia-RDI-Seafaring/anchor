"""OIP manifest for Anchor's bundled PDF producer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anchor import __version__

NAME = "anchor-pdfs"
DISPLAY_NAME = "Anchor PDFs"
VERSION = __version__
TOOLS_NAMESPACE = "pdf"


def manifest(data_dir: Path | None = None) -> dict[str, Any]:
    """Return the bundled PDF producer manifest."""
    return {
        "oip_version": "0.1",
        "producer": {
            "name": NAME,
            "display_name": DISPLAY_NAME,
            "version": VERSION,
            "homepage": "https://github.com/Novia-RDI-Seafaring/anchor",
        },
        "kind": "bundled-in-tree",
        "data_dir": str(data_dir) if data_dir else None,
        "produces": {
            "source_kinds": ["application/pdf"],
            "region_kinds": [
                "table",
                "spec_block",
                "chart",
                "diagram",
                "figure",
                "text",
            ],
            "source_ref_kinds": ["pdf-page-bbox"],
        },
        "invocation": {
            "kind": "mcp-stdio",
            "command": "anchor-mcp",
            "args": [],
            "tools_namespace": TOOLS_NAMESPACE,
        },
        "ui_hints": {
            "node_types": [
                {"name": "pdf:document", "renders": "document"},
                {"name": "pdf:spec_table", "renders": "spec_block regions"},
                {"name": "pdf:image", "renders": "figure/diagram regions"},
            ],
            "edge_styles": {
                "pdf:evidence": {"stroke": "#FF8E2B", "dasharray": "4 4"}
            },
            "source_ref_handlers": {
                "pdf-page-bbox": "open the PDF at the given page, draw the bbox"
            },
        },
    }
