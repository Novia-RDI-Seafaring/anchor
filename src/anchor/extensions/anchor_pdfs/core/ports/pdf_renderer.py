"""PdfRenderer protocol — PDF → page PNGs and region crops."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol


CropFormat = Literal["png", "svg", "pdf"]


class PdfRenderer(Protocol):
    async def render_pages(self, pdf_path: Path, dpi: int = 150) -> dict[int, bytes]: ...

    async def crop_region(
        self,
        pdf_path: Path,
        page: int,
        bbox: list[float],
        fmt: CropFormat = "png",
        dpi: int = 200,
    ) -> bytes: ...
