"""Fake protocol implementations for tests.

Function-style helpers (not pytest fixtures) — call them inline in tests.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.embedder import Embedder  # noqa: F401
from anchor.extensions.anchor_pdfs.core.ports.md_polisher import PageMdPolisher  # noqa: F401
from anchor.extensions.anchor_pdfs.core.ports.pdf_extractor import PdfExtractor  # noqa: F401
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import CropFormat, PdfRenderer  # noqa: F401
from anchor.extensions.anchor_pdfs.core.ports.region_extractor import RegionExtractor  # noqa: F401


class FakePdfExtractor:
    """Returns a pre-canned docling dict, ignoring the PDF entirely."""

    def __init__(self, docling: dict[str, Any] | None = None) -> None:
        self.docling = docling or {
            "items": [
                {"label": "title", "text": "Demo Doc", "page": 1, "bbox": [0, 700, 200, 720]},
                {"label": "section_header", "text": "Section A", "page": 1, "bbox": [0, 600, 100, 620]},
                {"label": "text", "text": "First paragraph.", "page": 1, "bbox": [0, 580, 200, 595]},
            ],
        }

    async def extract(self, pdf_path: Path) -> dict[str, Any]:
        return dict(self.docling)


class FakePdfRenderer:
    def __init__(self, page_count: int = 1) -> None:
        self.page_count = page_count

    async def render_pages(self, pdf_path: Path, dpi: int = 150) -> dict[int, bytes]:
        return {p: f"PNG-bytes-page-{p}".encode() for p in range(1, self.page_count + 1)}

    async def crop_region(
        self, pdf_path: Path, page: int, bbox: list[float], fmt: CropFormat = "png", dpi: int = 200,
    ) -> bytes:
        return f"CROP-{page}-{bbox}-{fmt}".encode()


class FakePolisher:
    """Returns the deterministic seed unchanged."""

    async def polish_page(
        self, *, page_image: bytes, page_no: int, deterministic_md: str,
        docling_items: list[dict[str, Any]], model: str,
    ) -> str:
        return deterministic_md


class FakeRegionExtractor:
    def __init__(self, regions_per_page: list[dict[str, Any]] | None = None) -> None:
        self._regions = regions_per_page or [
            {"id": "r1", "kind": "text", "title": "fake region", "description": "x", "bbox": [10, 600, 200, 580], "tags": [], "entities": []}
        ]

    async def extract_page(
        self, *, page_image: bytes, page_no: int, docling_items: list[dict[str, Any]], model: str,
    ) -> list[dict[str, Any]]:
        return [dict(r, page=page_no) for r in self._regions]


class FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), float(t.count(" "))] for t in texts]
