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

# ── Toolset: document reading tools ─────────────────────────────────────────

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()
_toolset.tool(document_tools.get_document_tree)
_toolset.tool(document_tools.read_document_page)
_toolset.tool(document_tools.get_document_full_text)
_toolset.tool(document_tools.get_document_page_count)


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
    """List available documents with metadata and pipeline status."""
    from src.knowledge_base.service import get_document_service, get_pipeline_status
    from src.agent.tools.product_data import (
        find_product_data_by_filename,
        find_product_index_by_filename,
    )

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
        filename = doc.get("filename", "")
        entry: dict[str, Any] = {
            "id": doc_id,
            "filename": filename,
            "status": doc.get("status", "unknown"),
            "pages": doc.get("node_count") or doc.get("chunk_count") or 0,
        }
        if doc_id == active_id:
            entry["active"] = True
        if doc_id in workspace_ids:
            entry["in_workspace"] = True

        # Pipeline progress (if currently running)
        pipeline = get_pipeline_status(filename)
        if pipeline:
            entry["pipeline"] = f"{pipeline['stage']} {pipeline['current']}/{pipeline['total']}"

        # Data availability
        has_gold = find_product_data_by_filename(filename) is not None
        has_index = find_product_index_by_filename(filename) is not None
        if has_gold:
            entry["data"] = "gold"
        elif has_index:
            entry["data"] = "index"
        else:
            entry["data"] = "none"

        doc_entries.append(entry)

    docs_json = json.dumps(doc_entries, indent=2, default=str)
    return f"AVAILABLE DOCUMENTS:\n```json\n{docs_json}\n```"


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

## Document data — three tiers

1. **Gold data** (in context) — pre-extracted structured product data with specs, tables,
   operating data, bboxes. Use directly without calling any tool.

2. **Silver index** (in context) — compact outline listing sections, tables (with header
   row + first-column values), and figures, each with page + bbox. Use it to decide
   which page to jump to with read_document_page.

3. **Silver page markdown** (in context as fallback) — per-page text when no gold/index
   is available.

## Document tools

- `get_document_tree(document_id?, filename?)` — get the table of contents (outline,
  tables, figures). Useful when the index wasn't pre-loaded into context.
- `read_document_page(document_id?, filename?, page_no, include_image?)` — read one page.
  Returns polished markdown + page image + gold regions (if available).
- `get_document_full_text(document_id?, filename?, include_pages?)` — get all page text
  at once. Use for full-document analysis or when you need multiple pages.
- `get_document_page_count(document_id?, filename?)` — get total page count.

## Strategy

- Gold data is authoritative — use it first when available, don't read pages.
- Index present? Jump directly to the relevant table/section page.
- Nothing loaded? Short docs (≤6 pages): use get_document_full_text. Longer: start
  with get_document_tree, then read specific pages.

## FMU wiring

- FMU nodes expose handles: inputs "in-{name}", outputs "out-{name}", parameters "param-in-{name}".
- Spec nodes expose per-row handles: "spec-row-out-{sectionIdx}-{rowIdx}" (right side).
- Wire with add_relation using source_handle and target_handle.
- Match by engineering meaning: "Temperature" → "temp_in", "Mass flow" → "mass_in", etc.
""".strip()


# ── Capability class ─────────────────────────────────────────────────────────

@dataclass
class ContextCapability(AbstractCapability[Any]):
    """Injects canvas state and document list, provides the read_document_page tool."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> list:
        return [_INSTRUCTIONS, _canvas_context, _documents_context, _loaded_documents_context]
