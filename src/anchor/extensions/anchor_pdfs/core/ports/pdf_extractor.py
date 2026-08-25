"""PdfExtractor protocol — PDF → docling-style JSON dict.

The output schema is the silver-format dict consumed by `core/ingest/silver.py`:
    {"items": [{"label": ..., "text": ..., "page": int, "bbox": [l,t,r,b], ...}, ...]}
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
