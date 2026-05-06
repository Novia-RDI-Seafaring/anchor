"""PdfExtractor protocol — PDF → docling-style JSON dict.

The output schema is the silver-format dict consumed by `core/ingest/silver.py`:
    {"items": [{"label": ..., "text": ..., "page": int, "bbox": [l,t,r,b], ...}, ...]}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class PdfExtractor(Protocol):
    async def extract(self, pdf_path: Path) -> dict[str, Any]: ...
