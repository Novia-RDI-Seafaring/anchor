"""Complete replacement page and polished-artifact membership."""
from typing import Any


def polished_membership(metadata: dict[str, Any]) -> list[int]:
    """Missing producer evidence means no proven polished pages (pre-G5)."""
    pages = metadata.get("polished_pages", [])
    if (not isinstance(pages, list) or any(type(p) is not int or p < 1 for p in pages)
            or len(pages) != len(set(pages))):
        raise ValueError("invalid polished page membership")
    return pages


def complete_pages(
    index: dict[str, Any], metadata: dict[str, Any], markdown: dict[int, str],
    candidates: dict[int, list[dict[str, Any]]], rendered: dict[int, bytes],
) -> list[int]:
    pages = sorted(rendered)
    if pages != list(range(1, len(pages) + 1)) or not set(candidates).issubset(pages):
        raise ValueError("replacement extraction and rendered page membership disagree")
    index["document"]["page_count"] = len(pages)
    metadata["page_count"] = len(pages)
    for page in pages:
        markdown.setdefault(page, "")
        candidates.setdefault(page, [])
        metadata["pages"].setdefault(str(page), {"item_count": 0, "labels": {}, "item_ids": [], "bbox_union": []})
    return pages
