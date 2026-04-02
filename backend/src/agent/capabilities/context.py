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


# ── Static instructions ──────────────────────────────────────────────────────

_INSTRUCTIONS = """
You have full visibility of the canvas state and available documents above.
To investigate a document, use read_document_page(document_id, page_no) — it returns
the page text and a rendered screenshot.
You can call it multiple times to explore.

Think like an engineer reading a document:
- Check the document list to find the right doc
- For short docs (≤6 pages), read all pages to understand the content
- For longer docs, start with page 1 (often has overview/TOC), then navigate to relevant sections
- Trust what you READ in the document over any other source
""".strip()


# ── Capability class ─────────────────────────────────────────────────────────

@dataclass
class ContextCapability(AbstractCapability[Any]):
    """Injects canvas state and document list, provides the read_document_page tool."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> list:
        return [_INSTRUCTIONS, _canvas_context, _documents_context]
