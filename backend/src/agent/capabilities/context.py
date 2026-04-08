"""Context capability — injects canvas state and available documents into the agent's context."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai._run_context import RunContext
from pydantic_ai.toolsets import FunctionToolset

from ..deps import AgentDeps
from ..tools import document as document_tools
from ..tools.product_data import (
    build_loaded_documents_context,
)

# ── Toolset: reading tools only ──────────────────────────────────────────────

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()
_toolset.tool(document_tools.read_document_page)


# ── Dynamic context injection ────────────────────────────────────────────────

def _canvas_context(ctx: RunContext[AgentDeps]) -> str | None:
    """Serialize current canvas state into the agent's context."""
    state = ctx.deps.state
    if not state.nodes and not state.relations:
        return "CANVAS STATE: empty (no nodes or relations yet)."

    nodes_summary = []
    for n in state.nodes:
        entry: dict[str, Any] = {"id": n.id, "type": n.node_type}
        if n.title:
            entry["title"] = n.title
        if n.text:
            entry["text"] = n.text[:120]
        if n.spec_title:
            entry["spec_title"] = n.spec_title
        if n.properties:
            entry["properties"] = len(n.properties)
        if n.funnel_label:
            entry["funnel_label"] = n.funnel_label
        if n.area_label:
            entry["area_label"] = n.area_label
        if n.parent_id:
            entry["parent_id"] = n.parent_id
        nodes_summary.append(entry)

    relations_summary = [
        {"from": r.from_id, "to": r.to_id, "label": r.label}
        for r in state.relations
    ]

    canvas_json = json.dumps(
        {"nodes": nodes_summary, "relations": relations_summary},
        indent=2,
        default=str,
    )
    return f"CANVAS STATE (current nodes and relations):\n```json\n{canvas_json}\n```"


async def _documents_context(ctx: RunContext[AgentDeps]) -> str | None:
    """List available documents with metadata."""
    from src.knowledge_base.service import get_document_service

    try:
        service = await get_document_service()
        documents = await service.list_documents()
    except Exception:
        return None

    if not documents:
        return "AVAILABLE DOCUMENTS: none loaded."

    workspace_ids = set(ctx.deps.state.workspace_doc_ids or [])
    active_id = ctx.deps.state.active_document_id

    doc_entries = []
    for doc in documents:
        doc_id = doc.get("document_id", "")
        entry: dict[str, Any] = {
            "id": doc_id,
            "filename": doc.get("filename", ""),
            "pages": doc.get("page_count", "?"),
            "chunks": doc.get("chunk_count", 0),
        }
        if doc_id == active_id:
            entry["active"] = True
        if doc_id in workspace_ids:
            entry["in_workspace"] = True
        doc_entries.append(entry)

    docs_json = json.dumps(doc_entries, indent=2, default=str)
    return (
        f"AVAILABLE DOCUMENTS:\n```json\n{docs_json}\n```\n"
        "Use read_document_page(document_id=..., page_no=N) to read any page."
    )


def _loaded_documents_context(ctx: RunContext[AgentDeps]) -> str | None:
    """Auto-load gold data and silver index for every document node on the canvas.

    - Gold (if present) is authoritative — the agent can answer without reading pages.
    - Index (always preferred when present) is a cheap TOC the agent uses to decide
      which page + bbox to open via read_document_page.
    """
    state = ctx.deps.state
    doc_nodes = [n for n in state.nodes if n.node_type == "document" and n.filename]
    if not doc_nodes:
        return None
    return build_loaded_documents_context([node.filename for node in doc_nodes])


# ── Static instructions ──────────────────────────────────────────────────────

_INSTRUCTIONS = """
You have full visibility of the canvas state and available documents above.

Documents on the canvas with pre-extracted gold-layer data are automatically loaded
into your context — you already have their full structured product data (specs, tables,
operating data, dimensions, bboxes, etc.). Use this data directly without calling any tool.
DO NOT call read_document_page for documents that have gold data loaded.

For documents WITHOUT gold data, you may instead receive a DOCUMENT INDEX — a compact
outline listing sections, tables (with header row + first-column values), and figures,
each stamped with `page` and `bbox`. Use the index to jump straight to the right page
and region via read_document_page(document_id, page_no) rather than scanning sequentially.
The `first_column_values` of each table often reveals whether it's per-model — e.g. rows
like ["LKH-5", "LKH-10", ...] tells you that's the table to open for per-model specs.

For documents without gold OR index data, use read_document_page to see the raw page.

Think like an engineer reading a document:
- Gold data is authoritative — use it first when available
- Index present? Open the specific page+bbox pointed to by the relevant table/section
- Nothing loaded? Short docs (≤6 pages), read all pages; longer docs, start with page 1

FMU wiring:
- FMU nodes expose handles for each variable: inputs "in-{name}",
  outputs "out-{name}", parameters "param-in-{name}".
- Spec nodes expose per-row handles: "spec-row-out-{sectionIdx}-{rowIdx}" (right side)
  and "spec-row-in-{sectionIdx}-{rowIdx}" (left side). Section/row indices are 0-based.
- To wire a spec row to an FMU input, use add_relation with
  source_handle="spec-row-out-{sectionIdx}-{rowIdx}" and target_handle="in-{varName}".
- Match by engineering meaning: e.g. "Temperature" spec → FMU "temp_in",
  "Mass flow" → "mass_in", etc.
""".strip()


# ── Capability class ─────────────────────────────────────────────────────────

@dataclass
class ContextCapability(AbstractCapability[Any]):
    """Injects canvas state and document list, provides the read_document_page tool."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> list:
        return [_INSTRUCTIONS, _canvas_context, _documents_context, _loaded_documents_context]
