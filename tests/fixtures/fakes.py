"""Fake protocol implementations for tests.

Function-style helpers (not pytest fixtures) — call them inline in tests.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import CropFormat


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


# A 1x1 transparent PNG — enough bytes for content-type tests without
# pulling Pillow at import time.
TINY_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xcf"
    b"\xc0\x00\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeSnapshotter:
    """SnapshotPort fake — returns either an on-disk path or inline bytes.

    Tests pick the mode they want via `mode="path"` (writes a tiny PNG
    under `out_dir`) or `mode="bytes"` (returns inline).
    """

    def __init__(
        self,
        *,
        mode: str = "bytes",
        out_dir: Path | None = None,
        payload: bytes | None = None,
    ) -> None:
        self.mode = mode
        self.out_dir = out_dir
        self.payload = payload if payload is not None else TINY_PNG_BYTES
        self.calls: list[dict[str, Any]] = []

    async def snapshot(
        self,
        slug: str,
        *,
        format: str = "png",
        viewport: tuple[int, int] | None = None,
        full_page: bool = True,
    ):
        from anchor.core.ports.snapshot import SnapshotResult

        self.calls.append({
            "slug": slug, "format": format, "viewport": viewport, "full_page": full_page,
        })
        ctype = "image/svg+xml" if format == "svg" else "image/png"
        if self.mode == "path":
            assert self.out_dir is not None, "FakeSnapshotter(mode='path') needs out_dir="
            self.out_dir.mkdir(parents=True, exist_ok=True)
            target = self.out_dir / f"{slug}.{format}"
            target.write_bytes(self.payload)
            return SnapshotResult(format=format, content_type=ctype, path=target)
        return SnapshotResult(format=format, content_type=ctype, bytes_=self.payload)
