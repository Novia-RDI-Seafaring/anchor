"""PdfRenderer implementation backed by PyMuPDF."""
from __future__ import annotations

import asyncio
from pathlib import Path

from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import CropFormat


class PymupdfPdfRenderer:
    async def render_pages(self, pdf_path: Path, dpi: int = 150) -> dict[int, bytes]:
        return await asyncio.to_thread(_render_pages_sync, pdf_path, dpi)

    async def crop_region(
        self,
        pdf_path: Path,
        page: int,
        bbox: list[float],
        fmt: CropFormat = "png",
        dpi: int = 200,
    ) -> bytes:
        return await asyncio.to_thread(_crop_region_sync, pdf_path, page, bbox, fmt, dpi)

    async def locate_text(
        self,
        pdf_path: Path,
        page: int,
        query: str,
        within_bbox: list[float] | None = None,
    ) -> list[list[float]]:
        return await asyncio.to_thread(
            _locate_text_sync, pdf_path, page, query, within_bbox
        )


def _render_pages_sync(pdf_path: Path, dpi: int) -> dict[int, bytes]:
    import pymupdf

    out: dict[int, bytes] = {}
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            out[i] = pix.tobytes("png")
    return out


def _crop_region_sync(pdf_path: Path, page_no: int, bbox: list[float], fmt: CropFormat, dpi: int) -> bytes:
    import pymupdf

    if len(bbox) != 4:
        raise ValueError("bbox must be [left, top, right, bottom] (BOTTOMLEFT)")
    left, top, right, bottom = bbox
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_no - 1]
        h = page.rect.height
        # Convert BOTTOMLEFT (gold/Docling) → PyMuPDF (TOPLEFT) and normalize.
        #
        # The 4-tuple element ORDER is not guaranteed: gold bboxes are stored
        # ascending-y ([x0, y0, x1, y1] with y0 < y1) for some documents and
        # descending-y for others. The bottom-left→top-left flip (h - y) then
        # produces an inverted rect (y0 > y1) for ascending-y input, which makes
        # PyMuPDF raise FzErrorArgument instead of returning a crop. Taking
        # min/max per axis mirrors the frontend's order-independent
        # `bboxToImageRect`, so any ordering yields a valid positive-area rect.
        x0, x1 = sorted((left, right))
        y0, y1 = sorted((h - top, h - bottom))
        rect = pymupdf.Rect(x0, y0, x1, y1)
        # A degenerate (zero/near-zero area) bbox would make PyMuPDF raise; surface
        # it as ValueError so the route maps it to 4xx, never a 500.
        if rect.width <= 1e-6 or rect.height <= 1e-6:
            raise ValueError(f"degenerate bbox: {bbox}")
        if fmt == "png":
            return page.get_pixmap(clip=rect, dpi=dpi).tobytes("png")
        elif fmt == "svg":
            return page.get_svg_image(matrix=pymupdf.Matrix(dpi / 72, dpi / 72)).encode()
        elif fmt == "pdf":
            new = pymupdf.open()
            new.insert_pdf(doc, from_page=page_no - 1, to_page=page_no - 1)
            new[0].set_cropbox(rect)
            return new.tobytes()
    raise ValueError(f"unknown fmt: {fmt}")


def _bottomleft_clip_rect(h: float, within_bbox: list[float]):
    """Build a PyMuPDF (TOPLEFT) clip rect from a BOTTOMLEFT region bbox.

    Mirrors `_crop_region_sync`: gold/region bboxes are stored in Docling's
    BOTTOMLEFT origin with an unguaranteed element order, so we sort per axis
    after the bottom-left->top-left flip and get a positive-area rect for any
    ordering.
    """
    import pymupdf

    if len(within_bbox) != 4:
        raise ValueError("within_bbox must be [left, top, right, bottom]")
    left, top, right, bottom = within_bbox
    x0, x1 = sorted((left, right))
    y0, y1 = sorted((h - top, h - bottom))
    return pymupdf.Rect(x0, y0, x1, y1)


def _locate_text_sync(
    pdf_path: Path,
    page_no: int,
    query: str,
    within_bbox: list[float] | None,
) -> list[list[float]]:
    import pymupdf

    query = (query or "").strip()
    if not query:
        return []
    with pymupdf.open(pdf_path) as doc:
        if page_no < 1 or page_no > doc.page_count:
            return []
        page = doc[page_no - 1]
        h = page.rect.height
        clip = None
        if within_bbox is not None:
            clip = _bottomleft_clip_rect(h, within_bbox)
            # A degenerate region clip would make search_for raise; treat it as
            # "no region constraint" rather than failing the locate.
            if clip.width <= 1e-6 or clip.height <= 1e-6:
                clip = None
        # PyMuPDF returns matches as TOPLEFT page-space rects.
        try:
            rects = page.search_for(query, clip=clip)
        except Exception:  # noqa: BLE001 - a search that PyMuPDF cannot run -> no match
            return []
        out: list[list[float]] = []
        for r in rects:
            # Convert TOPLEFT (PyMuPDF) -> BOTTOMLEFT (gold/Docling) so the
            # returned quad rides through the same `bboxToImageRect` mapping the
            # frontend uses for region bboxes. Emit ascending order per axis.
            x0, x1 = sorted((r.x0, r.x1))
            yb0, yb1 = sorted((h - r.y0, h - r.y1))
            out.append([x0, yb0, x1, yb1])
        return out
