"""Documents — shared substrate, not per-workspace."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

from anchor.adapters.http.deps import get_doc_store
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import SynopsisService

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _synopsis_svc(request: Request) -> SynopsisService:
    """Pulled off app.state by the http app factory."""
    svc = getattr(request.app.state, "synopsis_service", None)
    if svc is None:
        raise HTTPException(503, "synopsis service not configured")
    return svc


@router.get("")
async def list_documents(store: DocStore = Depends(get_doc_store)):
    return await store.list_documents()


@router.get("/{slug}/index")
async def get_index(slug: str, store: DocStore = Depends(get_doc_store)):
    out = await store.get_index(slug)
    if out is None:
        raise HTTPException(404)
    return out


@router.get("/{slug}/regions")
async def get_regions(slug: str, page: int | None = None, store: DocStore = Depends(get_doc_store)):
    return await store.get_regions(slug, page=page)


@router.get("/{slug}/gold-map")
async def get_gold_map(slug: str, store: DocStore = Depends(get_doc_store)):
    out = await store.get_gold_map(slug)
    if out is None:
        raise HTTPException(404)
    return out


@router.get("/{slug}/pages/{page}/text")
async def page_text(slug: str, page: int, store: DocStore = Depends(get_doc_store)):
    text = await store.get_page_text(slug, page)
    if text is None:
        raise HTTPException(404)
    return PlainTextResponse(text)


@router.get("/{slug}/pages/{page}/image")
async def page_image(slug: str, page: int, store: DocStore = Depends(get_doc_store)):
    p = await store.get_page_image_path(slug, page)
    if p is None:
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


@router.get("/{slug}/crops/{rel_path:path}")
async def crop(slug: str, rel_path: str, store: DocStore = Depends(get_doc_store)):
    p = await store.get_crop_path(slug, rel_path)
    if p is None:
        raise HTTPException(404)
    return FileResponse(p)


@router.get("/{slug}/pdf")
async def raw_pdf(slug: str, store: DocStore = Depends(get_doc_store)):
    """Serve the original bronze PDF.

    Architecturally: this is the producer's choice to expose the raw source
    material it stashed. Consumers (Anchor's PDF viewer today, a future
    PDF.js renderer, an agent that wants to feed the PDF to a vision model)
    can read this endpoint directly. Same-origin so no CORS dance.
    """
    path = await store.get_raw_pdf_path(slug)
    if path is None:
        raise HTTPException(404, f"raw PDF not available for slug: {slug}")
    # An in-memory store may return a `memory://...` pseudo-path. The HTTP
    # route can only serve a real file, so reject that explicitly — agents
    # against an in-memory backend should use the MCP `get_pdf` tool with
    # `format=base64` instead.
    if str(path).startswith("memory://"):
        raise HTTPException(501, "in-memory store cannot serve raw PDF over HTTP; use MCP get_pdf with format=base64")
    filename = path.name
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("/{slug}/synopsis")
async def synopsis_data(
    slug: str,
    entity: str = Query(..., description="Entity to scope the synopsis to, e.g. 'LKH-5'."),
    request: Request = None,  # type: ignore[assignment]
):
    """Return the structured SynopsisData JSON for an entity.

    Agents who want to render their own output (Marp, Notion, HTML, ...)
    consume this. For ready-made artefacts use /synopsis.pdf or
    /synopsis.md.
    """
    svc = _synopsis_svc(request)
    from dataclasses import asdict
    try:
        data = await svc.compose(slug=slug, entity=entity)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, str(e))
    return asdict(data)


@router.get("/{slug}/synopsis.pdf")
async def synopsis_pdf(
    slug: str,
    entity: str = Query(...),
    request: Request = None,  # type: ignore[assignment]
):
    """Return a multi-page PDF synopsis for the entity."""
    svc = _synopsis_svc(request)
    try:
        pdf_bytes = await svc.render_pdf(slug=slug, entity=entity)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, str(e))
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}-{entity}.pdf"'},
    )


@router.get("/{slug}/synopsis.md")
async def synopsis_md(
    slug: str,
    entity: str = Query(...),
    crop_url_base: str | None = Query(
        None, description="If set, crop images are referenced via this URL base.",
    ),
    request: Request = None,  # type: ignore[assignment]
):
    """Return a Marp-compatible markdown slide deck for the entity."""
    svc = _synopsis_svc(request)
    try:
        md = await svc.render_markdown(slug=slug, entity=entity, crop_url_base=crop_url_base)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, str(e))
    return PlainTextResponse(md, media_type="text/markdown")
