"""Delete a document from a project, saying first what cites it.

One operation for HTTP, MCP and the CLI. A document is cited when a canvas
shows it (a document card), a value names it as its source (a spec row, a
node's or an edge's ``source_ref``), or prose links to it (``anchor:<slug>``).
A cited document is not deleted unless asked to be (``force``): the answer
lists where it is cited instead. Deleting it anyway leaves those cards and
rows where they are; their source links then point nowhere and show as such,
so nothing on a canvas disappears silently.
"""
from __future__ import annotations

import json
from typing import Any

from anchor.core.services.workspace_service import WorkspaceService


def _names(ref: Any, slug: str) -> bool:
    return isinstance(ref, dict) and ref.get("slug") == slug


def _links(value: Any, slug: str) -> int:
    text = json.dumps(value, ensure_ascii=False)
    return text.count(f"anchor:{slug}?") + text.count(f"anchor://{slug}?")


async def find_citations(workspace: WorkspaceService, slug: str) -> list[dict[str, Any]]:
    """Every canvas that cites ``slug``, with what on it does."""
    out: list[dict[str, Any]] = []
    for summary in await workspace.list_workspaces():
        canvas = summary.get("slug")
        if not isinstance(canvas, str):
            continue
        state = await workspace.get_state(canvas)
        counts = {"cards": 0, "rows": 0, "values": 0, "links": 0, "edges": 0}
        for node in state.get("nodes") or []:
            data = node.get("data") or {}
            if node.get("node_type") == "document" and data.get("slug") == slug:
                counts["cards"] += 1
                continue
            rows = data.get("rows") if isinstance(data.get("rows"), list) else []
            counts["rows"] += sum(1 for row in rows if isinstance(row, dict) and _names(row.get("source_ref"), slug))
            if _names(data.get("source_ref"), slug) or data.get("source_doc_slug") == slug:
                counts["values"] += 1
            counts["links"] += _links(data, slug)
        for edge in state.get("edges") or []:
            if _names((edge.get("data") or {}).get("source_ref"), slug):
                counts["edges"] += 1
        counts["values"] += sum(
            1 for ref in (state.get("metadata") or {}).get("references") or []
            if isinstance(ref, dict) and _names(ref.get("source_ref"), slug)
        )
        if any(counts.values()):
            out.append({"canvas": canvas, "title": summary.get("title") or canvas,
                        **{k: v for k, v in counts.items() if v}})
    return out


async def delete_document(
    workspace: WorkspaceService, doc_store: Any, slug: str, *, force: bool = False,
) -> dict[str, Any]:
    """Delete ``slug`` unless it is cited and ``force`` is not given.

    Returns ``{deleted, slug, cited_by, ...}``; when not deleted, ``next``
    says how to go ahead. Raises ``KeyError`` for an unknown document and
    ``IngestLockHeld`` while it is being ingested.
    """
    if await doc_store.get_index(slug) is None and await doc_store.get_raw_pdf_path(slug) is None:
        raise KeyError(slug)
    cited_by = await find_citations(workspace, slug)
    if cited_by and not force:
        return {
            "deleted": False,
            "slug": slug,
            "cited_by": cited_by,
            "next": (
                "Canvases cite this document. Deleting it leaves their cards and "
                "rows in place with source links that point nowhere. Ask the "
                "user, then pass force to delete it anyway."
            ),
        }
    result = await doc_store.delete_document(slug)
    return {"deleted": True, **result, "cited_by": cited_by}
