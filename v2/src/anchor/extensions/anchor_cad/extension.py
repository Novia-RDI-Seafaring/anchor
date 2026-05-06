"""anchor_cad extension — OIP-compliant CAD producer + canvas integration.

Today (scaffold): the extension ships a real OIP manifest and the data
contracts (CadModel, CadParameter, CadPart, source_ref kinds). The
NaiveCadInspector fills only what can be known without a real parser
(filename-based kind detection, file-size triangle estimate for binary
STL, regex parameter extraction for JSCAD/OpenSCAD). Real STL/STEP/glTF
parsers are a follow-on; the manifest landing now means anchor_cad shows
up under `anchor extensions list` and the architecture's "future
producers" promise stops being aspirational.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anchor import __version__

NAME = "anchor-cad"
DISPLAY_NAME = "Anchor CAD"
VERSION = __version__
REQUIRES_CANVAS = ">=0.2,<0.3"
TOOLS_NAMESPACE = "cad"


def manifest(data_dir: Path | None = None) -> dict[str, Any]:
    """OIP manifest: what this producer ingests, produces, and how to call it.

    See OIP.md for the schema. Source kinds cover the common 3D / parametric
    formats; region kinds + source_ref_kinds describe the addressable units
    consumers will reference (parameters, parts, features).
    """
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
                "model/stl",
                "model/obj",
                "model/step+xml",
                "model/iges",
                "model/gltf-binary",
                "application/x-jscad",
                "application/x-openscad",
            ],
            "region_kinds": [
                "cad_parameter",
                "cad_part",
                "cad_assembly",
                "cad_feature",
                "cad_dimension",
                "cad_view_state",
            ],
            "source_ref_kinds": [
                "cad-parameter-name",
                "cad-part-id",
                "cad-feature-id",
            ],
        },
        "invocation": {
            "kind": "mcp-stdio",
            "command": "anchor-mcp",   # bundled — same MCP server hosts these tools
            "args": [],
            "tools_namespace": TOOLS_NAMESPACE,
        },
        "ui_hints": {
            "node_types": [
                {
                    "name": "cad:model",
                    "renders": "primitive:model3d",  # future: 3D viewport (three.js / model-viewer)
                    "fallback_render_hint": "card showing kind, parameter count, part count",
                },
                {
                    "name": "cad:parameter",
                    "renders": "primitive:concept",  # tunable value card
                    "fallback_render_hint": "card with parameter name, current value, unit",
                },
            ],
            "edge_styles": {
                "cad:wires": {"stroke": "#84CC16", "dasharray": "0"},
            },
            "source_ref_handlers": {
                "cad-parameter-name": "open the CAD model viewport, focus the parameter handle",
                "cad-part-id": "open the CAD model viewport, isolate the named part",
                "cad-feature-id": "open the CAD model viewport, highlight the feature",
            },
        },
    }


def build_service(
    data_dir: Path,
    bus: object,
    *,
    inspector: object | None = None,
):
    """Wire CadService with FS-backed storage and the naive inspector.

    Tests inject a MemoryCadStore + a fake inspector. Real STL/STEP parsers
    can replace `NaiveCadInspector` without touching the service or canvas.
    """
    from anchor.core.ports.event_bus import EventBus  # noqa: F401  (type hint)
    from anchor.extensions.anchor_cad.core.services import CadService
    from anchor.extensions.anchor_cad.infra.fs_store import FsCadStore
    from anchor.extensions.anchor_cad.infra.naive_inspector import NaiveCadInspector

    if inspector is None:
        inspector = NaiveCadInspector()

    return CadService(
        store=FsCadStore(data_dir),
        inspector=inspector,  # type: ignore[arg-type]
        bus=bus,  # type: ignore[arg-type]
    )
