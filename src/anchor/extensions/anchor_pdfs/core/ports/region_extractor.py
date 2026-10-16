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
        page_size: list[float] | None = None,
        dpi: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return a list of region dicts: kind, title, description, and geometry.

        ``docling_items`` are the page's candidates (``id``, ``label``,
        ``bbox`` in top-left points, ``text``). A region names its geometry by
        ``member_item_ids`` (candidate ids), or by an approximate ``bbox`` in
        points when no item covers it. ``page_size`` is the page in points
        and ``dpi`` the raster's resolution, so the extractor can tell the
        model what frame it is looking at.
        """
        raise NotImplementedError
