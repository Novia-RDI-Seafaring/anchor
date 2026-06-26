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
