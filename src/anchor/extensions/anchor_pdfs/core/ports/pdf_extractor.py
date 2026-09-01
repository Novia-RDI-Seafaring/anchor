"""PdfExtractor protocol — PDF → docling-style JSON dict.

The output schema is the silver-format dict consumed by `core/silver.py`:

    {
      "items": [{"label": ..., "text": ..., "page": int, "bbox": [l,t,r,b],
                 "cells"?: [{"row", "col", "text", "bbox"?}], ...}, ...],
      "pages": {page: {"width": float, "height": float}},   # PDF points
      "coord_origin": "top-left",                           # or "bottom-left"
    }

Coordinate contract (#281, mirrors OIP `pdf-page-bbox`): every bbox is in
**PDF points** (1/72 in, the page's own user space — never pixels or
normalised units), **top-left origin**, ``[left, top, right, bottom]`` with
``top <= bottom``. ``page`` is 1-based. ``pages`` is required so boxes can be
validated and converted.

An extractor that natively works in PDF user space may declare
``coord_origin: "bottom-left"`` instead of converting; the ingest boundary
(`silver.normalize_items`) flips it using ``pages``. That is the only other
accepted value. Labels use Anchor's normalized vocabulary (``text``,
``list_item``, ``table``, ``section_header``, ``title``, ``caption``,
``footnote``, ``picture``, ``page_header``, ``page_footer``, ...).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class PdfExtractor(Protocol):
    async def extract(
        self, pdf_path: Path, *, full_page_ocr: bool = False
    ) -> dict[str, Any]:
        """Extract a PDF to the silver-format dict.

        ``full_page_ocr`` opts into OCRing the whole page instead of only
        bitmap regions. It recovers text an extractor's default skips when a
        page has only a partial (or no) text layer. Default False keeps the
        fast born-digital path (issue #231).
        """
        raise NotImplementedError
