"""PdfRenderer implementation backed by PyMuPDF."""
from __future__ import annotations

import asyncio
from pathlib import Path

from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import CropFormat


class PymupdfPdfRenderer:
    async def render_pages(self, pdf_path: Path, dpi: int = 150) -> dict[int, bytes]:
        return await asyncio.to_thread(_render_pages_sync, pdf_path, dpi)

    async def page_sizes(self, pdf_path: Path) -> dict[int, tuple[float, float]]:
        return await asyncio.to_thread(_page_sizes_sync, pdf_path)

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
        raise ValueError("bbox must be [left, top, right, bottom] (top-left PDF points)")
    with pymupdf.open(pdf_path) as doc:
        page = doc[page_no - 1]
        # Region bboxes and PyMuPDF share the top-left convention (#281); only
        # normalise the element order so any y ordering yields a positive rect.
        rect = _clip_rect(bbox)
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


def _clip_rect(bbox: list[float]):
    """A PyMuPDF rect from a top-left region bbox, order-normalised per axis."""
    import pymupdf

    if len(bbox) != 4:
        raise ValueError("bbox must be [left, top, right, bottom]")
    left, top, right, bottom = bbox
    x0, x1 = sorted((left, right))
    y0, y1 = sorted((top, bottom))
    return pymupdf.Rect(x0, y0, x1, y1)


def _page_sizes_sync(pdf_path: Path) -> dict[int, tuple[float, float]]:
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        return {i: (float(p.rect.width), float(p.rect.height)) for i, p in enumerate(doc, start=1)}


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
        clip = None
        if within_bbox is not None:
            clip = _clip_rect(within_bbox)
            # A degenerate region clip would make search_for raise; treat it as
            # "no region constraint" rather than failing the locate.
            if clip.width <= 1e-6 or clip.height <= 1e-6:
                clip = None
        # PyMuPDF matches are already top-left page-space rects (#281): emit
        # them as-is, ascending per axis.
        try:
            rects = page.search_for(query, clip=clip)
        except Exception:  # noqa: BLE001 - a search that PyMuPDF cannot run -> no match
            return []
        out: list[list[float]] = []
        for r in rects:
            x0, x1 = sorted((r.x0, r.x1))
            y0, y1 = sorted((r.y0, r.y1))
            out.append([x0, y0, x1, y1])
        return out
