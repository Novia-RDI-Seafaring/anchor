"""PageMdPolisher protocol — VLM polishes deterministic page markdown."""
from __future__ import annotations

from typing import Any, Protocol


class PageMdPolisher(Protocol):
    async def polish_page(
        self,
        *,
        page_image: bytes,
        page_no: int,
        deterministic_md: str,
        docling_items: list[dict[str, Any]],
        model: str,
    ) -> str:
        raise NotImplementedError
