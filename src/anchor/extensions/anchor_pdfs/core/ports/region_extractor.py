"""RegionExtractor protocol — VLM extracts gold regions from a page."""
from __future__ import annotations

from typing import Any, Protocol


class RegionExtractor(Protocol):
    async def extract_page(
        self,
        *,
        page_image: bytes,
        page_no: int,
        docling_items: list[dict[str, Any]],
        model: str,
    ) -> list[dict[str, Any]]:
        """Return a list of region dicts with kind, bbox (approx), title, description, etc."""
        raise NotImplementedError
