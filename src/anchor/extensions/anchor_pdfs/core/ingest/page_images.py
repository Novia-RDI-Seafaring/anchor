"""Persist page rasters and their silver-candidate debug views together."""
from __future__ import annotations

import math
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.pdf_renderer import PdfRenderer


def _page_size(metadata: dict[str, Any], page: int) -> tuple[float, float] | None:
    entry = metadata.get("pages", {}).get(str(page), {})
    size = entry.get("page_size")
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        return None
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or value <= 0
        for value in size
    ):
        return None
    return float(size[0]), float(size[1])


async def write_page_images(
    store: DocStore,
    renderer: PdfRenderer,
    slug: str,
    page_pngs: dict[int, bytes],
    page_candidates: dict[int, list[dict[str, Any]]],
    pages_meta: dict[str, Any],
) -> None:
    for page, png in page_pngs.items():
        await store.write_silver_artifact(slug, f"pages/{page}.png", png)
        overlay = await renderer.render_candidate_overlay(
            png, page_candidates.get(page, []), page_size=_page_size(pages_meta, page),
        )
        await store.write_silver_artifact(slug, f"pages/{page}.candidates.png", overlay)
