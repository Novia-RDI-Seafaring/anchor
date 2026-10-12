"""Complete replacement page and polished-artifact membership."""
from typing import Any


def require_page_items(
    items: list[dict[str, Any]] | None, candidates: list[dict[str, Any]] | None,
    metadata: dict[str, Any], page: int,
) -> None:
    """New generations require the full evidence and preview IDs to agree."""
    expected = metadata.get("pages", {}).get(str(page), {}).get("item_ids")
    if (items is None or candidates is None or not isinstance(expected, list)
            or any(not isinstance(item, dict) for item in items)
            or any(not isinstance(candidate, dict) for candidate in candidates)
            or [item.get("id") for item in items] != expected
            or [candidate.get("id") for candidate in candidates] != expected
            or any(type(item.get("page")) is not int or item["page"] != page or item.get("id") != f"p{page}-i{i}"
                   for i, item in enumerate(items))):
        raise ValueError("replacement silver items are incomplete or inconsistent")


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
