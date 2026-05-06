"""Documents — shared substrate, not per-workspace."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from anchor.adapters.http.deps import get_doc_store
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore

router = APIRouter(prefix="/api/documents", tags=["documents"])


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
