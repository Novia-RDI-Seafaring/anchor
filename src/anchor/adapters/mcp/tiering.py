"""Tiered MCP tool surface (anchor#133).

The Anchor MCP server can dispatch ~50 tools, but advertising all of them at
once drowns the tool-search / progressive-disclosure layer some harnesses
(Claude Desktop) apply to large servers: a plain "create a project" request
runs several rounds of search before the exact tool ranks. The fix is to keep
*everything callable* but shrink what the server *advertises by default*.

Mechanism
=========
1. A small always-on CORE (~15 tools) covers the 90% path: lifecycle,
   document read, semantic search, and the canvas verbs an agent reaches for
   first. These are advertised on every connection.
2. The long tail (rare canvas ops, the harness ingest sub-protocol, FMU / CAD
   / SysML extension tools, derive/embed/synopsis) is GATED. It is advertised
   only when an extension is actually *active* for the resolved default
   project (it has data), and is always reachable through the
   ``anchor_list_capabilities`` meta-tool below.
3. Gating only changes ADVERTISEMENT. ``server.call_tool`` routes by tool name
   independently of the advertised list, so a gated tool stays callable the
   moment a harness discovers it. Nothing here deletes or renames a tool.

Why advertisement, not dispatch
===============================
The MCP ``list_tools`` handler is connection-level: it has no per-call
``project`` argument, so it cannot resolve a project the way ``call_tool``
does. We therefore gate against the *resolved default* project (session
default or the environment default) -- the project the agent is most likely
acting on. If that resolution is unavailable (e.g. an un-initialized
environment), we simply advertise the core; the long tail is still one
``anchor_list_capabilities`` call away.
"""
from __future__ import annotations

from typing import Any

# -- Core tool names (always advertised) -------------------------------------
#
# Kept as plain name sets so the curated core stays readable and so a test can
# assert the advertised surface without reconstructing descriptions.

CORE_LIFECYCLE_NAMES: set[str] = {
    "list_projects",
    "create_project",
}

CORE_STATUS_NAMES: set[str] = {
    "anchor_status",
}

# The 90%-path document tools: ingest, list, read, and semantic search.
CORE_PDF_NAMES: set[str] = {
    "ingest_pdf",
    "list_documents",
    "get_document_index",
    "get_gold_regions",
    "get_page_text",
    "get_crop",
    "search_documents",
    "extract_pointed",
}

# The agent intent queue (#148): the agent's inbox of user canvas actions
# (drop-to-ingest, ...) waiting to be handled. A primary agent workflow, so it
# is advertised on every connection rather than gated behind capability
# discovery.
CORE_INTENT_NAMES: set[str] = {
    "list_pending_intents",
    "next_intent",
    "resolve_intent",
}

# The canvas verbs an agent reaches for first.
CORE_CANVAS_NAMES: set[str] = {
    "canvas_create_workspace",
    "canvas_get_state",
    "canvas_add_node",
    "canvas_update_node",
    "canvas_add_edge",
    "canvas_snapshot",
}

# The capability-discovery meta-tool is itself core.
CAPABILITIES_TOOL_NAME = "anchor_list_capabilities"

CORE_NAMES: set[str] = (
    CORE_LIFECYCLE_NAMES
    | CORE_STATUS_NAMES
    | CORE_PDF_NAMES
    | CORE_INTENT_NAMES
    | CORE_CANVAS_NAMES
    | {CAPABILITIES_TOOL_NAME}
)


CAPABILITIES_TOOL_DEFINITION: dict[str, Any] = {
    "name": CAPABILITIES_TOOL_NAME,
    "description": (
        "List the extended Anchor tools that are not advertised by default, "
        "grouped by capability (harness ingestion, FMU simulation, CAD models, "
        "SysML diagrams, advanced canvas, extra document ops), with a one-line "
        "'when to use' for each. Call this when the small default tool set does "
        "not cover what you need; every listed tool is callable by name right "
        "away."
    ),
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}


# -- Capability groups (for anchor_list_capabilities) ------------------------
#
# Each group names a slice of the gated surface plus guidance. The "names" are
# resolved against the live definitions so descriptions stay single-sourced.

_CAPABILITY_GROUPS: list[dict[str, Any]] = [
    {
        "capability": "harness_ingest",
        "when_to_use": (
            "Ingest a PDF without an API key by polishing each page yourself "
            "(the agent drives extraction; the server does the mechanical half)."
        ),
        "names": [
            "ingest_begin",
            "ingest_get_page",
            "ingest_submit_page",
            "ingest_status",
            "ingest_finalize",
            "ingest_abort",
        ],
    },
    {
        "capability": "document_advanced",
        "when_to_use": (
            "Less common document operations: full gold map, page images, the "
            "raw PDF, embedding backfill, OIP-derived regions, synopsis, and "
            "live ingest-activity polling."
        ),
        "names": [
            "list_active_ingests",
            "get_ingest_status",
            "get_gold_map",
            "get_page_image",
            "get_pdf",
            "embed_document",
            "derive_region",
            "get_embeddings_meta",
            "compose_synopsis",
        ],
    },
    {
        "capability": "canvas_advanced",
        "when_to_use": (
            "Less common canvas operations: remove/clear, edge edits, layout "
            "(organize/align/distribute), sub-canvases, workspace management, "
            "and placeholder enumeration."
        ),
        "names": [
            "canvas_remove_node",
            "canvas_remove_edge",
            "canvas_update_edge",
            "canvas_clear",
            "canvas_delete_workspace",
            "canvas_list_workspaces",
            "canvas_organize_subtree",
            "canvas_align",
            "canvas_distribute",
            "canvas_create_sub_canvas",
            "canvas_list_placeholders",
        ],
    },
    {
        "capability": "lifecycle_advanced",
        "when_to_use": (
            "Environment + project administration beyond list/create: make a "
            "new environment, set the session default project, edit a project's "
            "description."
        ),
        "names": [
            "create_environment",
            "open_project",
            "update_project",
        ],
    },
    {
        "capability": "fmu",
        "when_to_use": "Inspect and simulate FMU models in this project.",
        "extension": "fmu",
        "names": [
            "fmu_inspect",
            "fmu_list_models",
            "fmu_get_model",
            "fmu_simulate",
            "fmu_get_results",
            "fmu_list_simulations",
        ],
    },
    {
        "capability": "cad",
        "when_to_use": "Inspect CAD models and tweak their parameters in this project.",
        "extension": "cad",
        "names": [
            "inspect",
            "list_models",
            "get_model",
            "set_parameter",
        ],
    },
    {
        "capability": "sysml",
        "when_to_use": "Render and export SysML diagrams from the canvas.",
        "extension": "sysml",
        "names": [
            "sysml_render",
            "sysml_export",
        ],
    },
]


def build_capabilities_payload(
    all_definitions: list[dict[str, Any]],
    *,
    active_extensions: set[str],
) -> dict[str, Any]:
    """Describe the gated long tail for ``anchor_list_capabilities``.

    ``all_definitions`` is the complete dispatchable surface (core + gated),
    so descriptions are single-sourced. ``active_extensions`` flags which
    extension groups currently have data in the resolved project; an inactive
    extension is still listed (so the agent can discover it) but tagged
    ``active: false``.
    """
    by_name = {d["name"]: d for d in all_definitions}
    groups: list[dict[str, Any]] = []
    for group in _CAPABILITY_GROUPS:
        tools = [
            {"name": name, "description": by_name[name]["description"]}
            for name in group["names"]
            if name in by_name
        ]
        if not tools:
            continue
        entry: dict[str, Any] = {
            "capability": group["capability"],
            "when_to_use": group["when_to_use"],
            "tools": tools,
        }
        ext = group.get("extension")
        if ext is not None:
            entry["extension"] = ext
            entry["active"] = ext in active_extensions
        groups.append(entry)
    return {
        "note": (
            "These tools are callable by name right now even though they are "
            "not advertised in the default tool list. Extension groups with "
            "'active': true also auto-appear in the default list because this "
            "project has data for them."
        ),
        "capabilities": groups,
    }


def select_advertised(
    all_definitions: list[dict[str, Any]],
    *,
    active_extensions: set[str],
    extension_names: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """Pick the advertised subset: core + any active extension's tools.

    ``all_definitions`` preserves the canonical order of the full surface.
    ``extension_names`` maps an extension key ("fmu" / "cad" / "sysml") to its
    tool names; an extension's tools are advertised only when it is active for
    the resolved project. Every other gated tool stays out of the default list
    but remains callable and discoverable via ``anchor_list_capabilities``.
    """
    advertise: set[str] = set(CORE_NAMES)
    for ext, names in extension_names.items():
        if ext in active_extensions:
            advertise |= names
    return [d for d in all_definitions if d["name"] in advertise]
