"""Quality diagnostics for deterministic Silver extraction."""

from __future__ import annotations

from typing import Any

# A page with fewer than this many non-whitespace extractable characters is
# treated as having no usable text layer.
LOW_TEXT_CHAR_THRESHOLD = 20


def _page_text_len(items: list[dict[str, Any]], page: int) -> int:
    """Count non-whitespace text emitted for one page."""
    total = 0
    for item in items:
        if not isinstance(item, dict) or item.get("page") != page:
            continue
        text = item.get("text")
        if isinstance(text, str):
            total += len("".join(text.split()))
        for cell in item.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            cell_text = cell.get("text")
            if isinstance(cell_text, str):
                total += len("".join(cell_text.split()))
    return total


def find_low_text_pages(
    docling: dict[str, Any],
    page_count: int,
    *,
    threshold: int = LOW_TEXT_CHAR_THRESHOLD,
) -> list[int]:
    """Return pages with too little extractable text."""
    items = docling.get("items")
    if not isinstance(items, list) or page_count <= 0:
        return []
    return [
        page
        for page in range(1, page_count + 1)
        if _page_text_len(items, page) < threshold
    ]


def low_text_pages_warning(pages: list[int]) -> str | None:
    """Build a non-fatal warning with the full-page OCR remedy."""
    if not pages:
        return None
    joined = ", ".join(str(page) for page in pages)
    noun = "Page" if len(pages) == 1 else "Pages"
    return (
        f"{noun} {joined} had little or no extractable text (likely no text "
        "layer / vector or scanned content). Retry with full-page OCR "
        "(anchor ingest --full-page-ocr / ingest_pdf full_page_ocr=true)."
    )
