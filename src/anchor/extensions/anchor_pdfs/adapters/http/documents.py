"""Documents — shared substrate, not per-workspace."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from anchor.adapters.http.deps import get_doc_store, get_ingest_service
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService, SynopsisService

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DeriveRegionBody(BaseModel):
    parent_region_id: str
    region: dict


class ExtractPointedBody(BaseModel):
    select: dict | None = None
    shape: Any


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


@router.get("/{slug}/pages/{page}/crop")
async def page_crop(
    slug: str,
    page: int,
    bbox: str = Query(..., description="Comma-separated [left, top, right, bottom] bbox."),
    dpi: int = Query(300, ge=72, le=600),
    store: DocStore = Depends(get_doc_store),
    ingest: IngestService = Depends(get_ingest_service),
):
    path = await store.get_raw_pdf_path(slug)
    if path is None:
        raise HTTPException(404, f"raw PDF not available for slug: {slug}")
    if str(path).startswith("memory://"):
        raise HTTPException(501, "in-memory store cannot crop raw PDF over HTTP")
    try:
        values = [float(part.strip()) for part in bbox.split(",")]
    except ValueError as e:
        raise HTTPException(400, "bbox must contain four numeric values") from e
    if len(values) != 4:
        raise HTTPException(400, "bbox must contain four numeric values")
    try:
        png = await ingest.renderer.crop_region(path, page, values, fmt="png", dpi=dpi)
    except (IndexError, ValueError) as e:
        # Bad bbox input (wrong arity, degenerate region): client error.
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # noqa: BLE001
        # Any renderer/PyMuPDF failure (e.g. an inverted or out-of-bounds rect
        # raising FzErrorArgument) is a request the renderer cannot fulfil, not a
        # server fault. Return 422 with the message so the caller (and the canvas
        # node's <img> onError fallback) sees a clean 4xx instead of a 500.
        raise HTTPException(422, f"could not crop region: {e}") from e
    return Response(png, media_type="image/png")


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
        raise HTTPException(404, str(e)) from e
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
        raise HTTPException(404, str(e)) from e
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
        raise HTTPException(404, str(e)) from e
    return PlainTextResponse(md, media_type="text/markdown")


@router.post("/{slug}/embed")
async def embed_document(
    slug: str,
    ingest: IngestService = Depends(get_ingest_service),
    store: DocStore = Depends(get_doc_store),
    overwrite: bool = Query(False, description="Re-embed even if embeddings.json already exists."),
):
    """Embed gold regions of a document and persist embeddings.json.

    Auto-runs at the end of `POST /workspaces/.../upload`; this endpoint
    backfills already-ingested docs without re-running the full pipeline.
    """
    if ingest.embedder is None:
        raise HTTPException(503, "no embedder wired — install sentence-transformers")
    existing = await store.get_embeddings(slug)
    if existing and not overwrite:
        return {"slug": slug, "skipped": True, "reason": "already embedded", "embed_model": existing.get("embed_model")}
    n = await ingest.embed_document(slug)
    return {"slug": slug, "embedded": n, "embed_model": ingest.embed_model_id}


@router.post("/{slug}/derived-regions")
async def derive_region(
    slug: str,
    body: DeriveRegionBody,
    ingest: IngestService = Depends(get_ingest_service),
):
    """Persist a region derived from an existing gold region.

    The consumer side of an OIP region producer: inherits the parent's
    source_ref (provenance) and records derived_from, then stores it durably.
    Re-run `POST /{slug}/embed` to make the new region searchable.
    """
    try:
        return await ingest.derive_region(slug, body.parent_region_id, body.region)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post("/{slug}/extract")
async def extract_pointed(
    slug: str,
    body: ExtractPointedBody,
    ingest: IngestService = Depends(get_ingest_service),
):
    """Pointed extraction: selected regions/entities into a caller shape.

    Resolves `select` ({regions, pages, entity}) to gold regions and fills
    `shape` (by-example or JSON Schema) from their cells, returning
    `{doc_slug, data, provenance, unfilled}`. Every filled leaf carries a
    `source_ref` provenance entry; unfillable leaves are listed in
    `unfilled` and never guessed. 404 when the document has no gold layer.
    """
    from anchor.extensions.anchor_pdfs.core.pointed_extraction import (
        PointedExtractionError,
    )
    try:
        return await ingest.extract_pointed(slug, select=body.select, shape=body.shape)
    except PointedExtractionError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/_search")
async def search_documents(
    q: str = Query(..., min_length=1),
    k: int = Query(10, ge=1, le=100),
    ingest: IngestService = Depends(get_ingest_service),
):
    """Semantic search across every embedded document.

    Returns `{query, embed_model, k, doc_count, hits: [...], skipped: [...]}`
    so callers can verify the model before consuming hits. `skipped`
    names embedded documents ignored because their stored embed_model
    does not match the query embedder.
    """
    if ingest.embedder is None:
        raise HTTPException(503, "no embedder wired")
    try:
        return await ingest.search(q, k=k)
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e


@router.get("/{slug}/embeddings/meta")
async def embeddings_meta(slug: str, store: DocStore = Depends(get_doc_store)):
    """Return embeddings.json metadata (without the vector payload).

    Useful for the browser to check which embed_model was used so it can
    load the matching WASM bundle before issuing semantic queries.
    """
    data = await store.get_embeddings(slug)
    if data is None:
        raise HTTPException(404, f"no embeddings for {slug}")
    return {
        "slug": slug,
        "embed_model": data.get("embed_model"),
        "dim": data.get("dim"),
        "embedded_at": data.get("embedded_at"),
        "vector_count": len(data.get("vectors", [])),
    }
