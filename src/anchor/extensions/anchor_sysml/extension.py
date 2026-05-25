"""anchor_sysml extension — OIP-compliant SysML v2 producer.

Phase 1 scope: textual SysML v2 (.sysml) → canvas nodes (``sysml:block``,
``sysml:requirement``, ``sysml:package``) + edges with descriptive
``data.marker`` values. Action / state / transition / flow / calc
constructs in the GfSE corpus are recognised but not mapped (a Diagnostic
is emitted instead).

The OIP manifest publishes the source / region / source_ref kinds so an
agent can address an extracted SysML element by its qualified name.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anchor import __version__

NAME = "anchor-sysml"
DISPLAY_NAME = "Anchor SysML v2"
VERSION = __version__
REQUIRES_CANVAS = ">=0.2,<0.3"
TOOLS_NAMESPACE = "sysml"


def manifest(data_dir: Path | None = None) -> dict[str, Any]:
    """OIP manifest for the SysML extension."""
    return {
        "oip_version": "0.1",
        "producer": {
            "name": NAME,
            "display_name": DISPLAY_NAME,
            "version": VERSION,
            "homepage": "https://github.com/Novia-RDI-Seafaring/anchor-kb-ui-RAG",
        },
        "kind": "bundled-in-tree",
        "data_dir": str(data_dir) if data_dir else None,
        "produces": {
            "source_kinds": [
                "text/sysml",
                "application/x-sysml",
            ],
            "region_kinds": [
                "sysml_package",
                "sysml_block",
                "sysml_requirement",
                "sysml_port",
                "sysml_attribute",
                "sysml_interface",
            ],
            "source_ref_kinds": [
                "sysml-text",
            ],
        },
        "invocation": {
            "kind": "mcp-stdio",
            "command": "anchor-mcp",
            "args": [],
            "tools_namespace": TOOLS_NAMESPACE,
        },
        "ui_hints": {
            "node_types": [
                {
                    "name": "sysml:block",
                    "renders": "card with attributes + ports + parts",
                    "fallback_render_hint": "card showing qualified_name + attribute count",
                },
                {
                    "name": "sysml:requirement",
                    "renders": "requirement card with subject + assert constraints",
                    "fallback_render_hint": "card showing req_id + short_name",
                },
                {
                    "name": "sysml:package",
                    "renders": "area or grouping card",
                    "fallback_render_hint": "card showing qualified_name",
                },
            ],
            "edge_styles": {
                "sysml:inheritance": {"stroke": "#6366F1", "dasharray": "0"},
                "sysml:satisfy": {"stroke": "#10B981", "dasharray": "4 2"},
                "sysml:interface-connection": {"stroke": "#F59E0B", "dasharray": "0"},
            },
            "source_ref_handlers": {
                "sysml-text": "open the SysML text panel, jump to (file, line, col)",
            },
        },
    }


def build_service(
    data_dir: Path,
    bus: object,
    *,
    workspace: object,
    parser: object | None = None,
    mapper: object | None = None,
    renderer: object | None = None,
):
    """Wire ``SysmlService`` against the canvas ``WorkspaceService``.

    ``data_dir`` is currently unused (no bronze/silver/gold layout for SysML
    in Phase 1) — kept on the signature so callers stay symmetric with the
    other extensions and so a future layout has a place to land.
    """
    from anchor.core.ports.event_bus import EventBus  # noqa: F401  (type hint)
    from anchor.core.services.workspace_service import WorkspaceService  # noqa: F401
    from anchor.extensions.anchor_sysml.core.services import SysmlService
    from anchor.extensions.anchor_sysml.infra.canvas_mapper import SysmlCanvasMapper
    from anchor.extensions.anchor_sysml.infra.parser import SysmlTextParser

    del data_dir  # reserved for Phase 2 (see docstring).
    return SysmlService(
        workspace=workspace,  # type: ignore[arg-type]
        bus=bus,  # type: ignore[arg-type]
        parser=parser or SysmlTextParser(),  # type: ignore[arg-type]
        mapper=mapper or SysmlCanvasMapper(),  # type: ignore[arg-type]
        renderer=renderer,  # type: ignore[arg-type]
    )
