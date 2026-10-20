"""``DELETE /api/documents/{slug}``: delete a document from the project.

Lives with the core routers, not the PDF extension's, because what decides
it is the canvases: a cited document is only deleted with ``force``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from anchor.adapters.document_delete import delete_document, find_citations
from anchor.extensions.anchor_pdfs.core.ports.doc_store import IngestLockHeld

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.delete("/{slug}")
async def delete_document_route(slug: str, request: Request, force: bool = False):
    """Delete ``slug``, or say which canvases cite it (409) unless ``force``."""
    try:
        out = await delete_document(
            request.app.state.workspace_service, request.app.state.doc_store, slug, force=force,
        )
    except KeyError:
        raise HTTPException(404, f"no document {slug!r} in this project") from None
    except IngestLockHeld:
        raise HTTPException(409, f"{slug!r} is being ingested; delete it when that finishes") from None
    if not out["deleted"]:
        raise HTTPException(409, detail=out)
    return out


@router.get("/{slug}/citations")
async def document_citations_route(slug: str, request: Request):
    """Which canvases cite ``slug``, and what on each: what a delete would leave pointing nowhere."""
    return {"slug": slug, "cited_by": await find_citations(request.app.state.workspace_service, slug)}
