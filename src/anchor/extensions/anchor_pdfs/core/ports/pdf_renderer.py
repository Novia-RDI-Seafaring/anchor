"""PdfRenderer protocol — PDF → page PNGs and region crops."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol


CropFormat = Literal["png", "svg", "pdf"]


class PdfRenderer(Protocol):
    async def render_pages(self, pdf_path: Path, dpi: int = 150) -> dict[int, bytes]:
        raise NotImplementedError

    async def crop_region(
        self,
        pdf_path: Path,
        page: int,
        bbox: list[float],
        fmt: CropFormat = "png",
        dpi: int = 200,
    ) -> bytes:
        raise NotImplementedError

    async def locate_text(
        self,
        pdf_path: Path,
        page: int,
        query: str,
        within_bbox: list[float] | None = None,
    ) -> list[list[float]]:
        """Find where ``query`` appears on ``page`` and return its quad(s).

        Each match is a page-space ``[left, top, right, bottom]`` rect in the
        same ascending-y, top-left coordinate convention the region overlays
        use (so a returned quad lines up with how the frontend draws region
        bboxes). ``within_bbox`` clips the search to a region to disambiguate
        a value that repeats elsewhere on the page; pass ``None`` to search the
        whole page. Returns ``[]`` when the text is not found (the caller then
        falls back to the region-level highlight).
        """
        raise NotImplementedError
