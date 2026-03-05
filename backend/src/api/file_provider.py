# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""File/screenshot helper API routes."""
from typing import Any, List, Optional, cast

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse

from src.api.file_service import get_file_service
from src.kb_engine.rag_engine import get_rag_engine
from src.kb_engine.search_models import PdfSearchResponse
from src.kb_engine.utils.pdf_rendering import render_pdf_page_to_image_bytes

router = APIRouter(prefix="/api", tags=["files"])

@router.get("/documents/pdf/search", response_model=PdfSearchResponse)
async def get_document_hases(
    q: str = Query(..., description="Text to search for in PDFs"),
):
    rag_engine = get_rag_engine()
    return rag_engine.query(f"Search for: {q}")


@router.get("/documents/pdf/screenshot", response_class=Response)
def get_pdf_screenshot(
    filename: str = Query(..., description="Filename of the PDF"),
    page_no: Optional[int] = Query(None, description="1-indexed PDF page number"),
    phrase: Optional[List[str]] = Query(None, description="Optional phrase(s) to underline"),
    bbox_l: Optional[float] = Query(None, description="Optional crop bbox left"),
    bbox_t: Optional[float] = Query(None, description="Optional crop bbox top"),
    bbox_r: Optional[float] = Query(None, description="Optional crop bbox right"),
    bbox_b: Optional[float] = Query(None, description="Optional crop bbox bottom"),
    bbox_coord_origin: str = Query("BOTTOMLEFT", description="BBox coord origin"),
):
    """Render a PDF page to PNG, with optional phrase highlights."""
    path = get_file_service().get_file_path(filename)
    crop_parts = [bbox_l, bbox_t, bbox_r, bbox_b]
    has_some_bbox = any(part is not None for part in crop_parts)
    has_all_bbox = all(part is not None for part in crop_parts)
    if has_some_bbox and not has_all_bbox:
        raise HTTPException(status_code=400, detail="Provide all bbox values: bbox_l,bbox_t,bbox_r,bbox_b")

    crop_bbox: dict[str, Any] | None = None
    if has_all_bbox:
        l = cast(float, bbox_l)
        t = cast(float, bbox_t)
        r = cast(float, bbox_r)
        b = cast(float, bbox_b)
        crop_bbox = {
            "l": float(l),
            "t": float(t),
            "r": float(r),
            "b": float(b),
            "coord_origin": bbox_coord_origin,
        }

    image_bytes = render_pdf_page_to_image_bytes(
        pdf_path=path,
        page_no=page_no or 1,
        phrases=phrase,
        crop_bbox=crop_bbox,
    )
    return Response(content=image_bytes, media_type="image/png")


@router.get("/documents/pdf/serve", response_class=Response)
def serve_pdf(
    filename: str = Query(..., description="Filename of the PDF"),
):
    path = get_file_service().get_file_path(filename)
    return FileResponse(path=path, media_type="application/pdf")