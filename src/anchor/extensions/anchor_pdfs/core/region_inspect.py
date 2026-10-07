"""Region inspection read-ops (#242 P1): the search -> inspect -> answer path.

`search_documents` returns ranked gold regions by `slug`/`region_id`. These two
ops let an agent then pull one region without paging the whole document:

- `inspect_region(slug, region_id)` -> the region's full record (kind, title,
  description, bbox, geometry, members, tags, entities, cells) plus a derived
  `source_ref` for grounding.
- `get_region_content(slug, region_id)` -> the region's reconstructed content
  (markdown + table cells), rebuilt from silver candidates when the region
  stored none.

Backed by the selected DocStore generation. Region ids are per-page
(`r1`, `r2`, ...); the token may be `p2/r4`, `2/r4`, or a unique bare `r4`.
Missing, malformed and ambiguous locators return no result.
"""
from __future__ import annotations

from typing import Any

from anchor.extensions.anchor_pdfs.core.pointed_extraction import _parse_region_token
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.silver import region_content_from_items
from anchor.extensions.anchor_pdfs.core.table_topology import topology_status


class AmbiguousRegionError(ValueError):
    """A bare region id matched regions on more than one page (#287).

    Region ids are only unique per page (``r1`` exists on page 1 *and*
    page 4), so silently picking the first match binds provenance to the
    wrong region. Carries the colliding ``region_id`` and the sorted
    candidate ``pages`` so adapters can render a structured error; the
    message tells the caller to qualify the page (``p<page>/<id>``).
    """

    def __init__(self, message: str, *, region_id: str, pages: list[int]) -> None:
        super().__init__(message)
        self.region_id = region_id
        self.pages = pages


async def find_region(
    store: DocStore, slug: str, region_id: str, *, raise_ambiguous: bool = False
) -> tuple[int, dict[str, Any]] | None:
    """Resolve exactly one stored region, using the store's page membership."""
    page_hint, rid = _parse_region_token(region_id)
    if not rid or ("/" in region_id and (page_hint is None or page_hint < 1)):
        return None
    gold = await store.get_regions(slug, page_hint)
    pages = gold.get("pages", {}) if isinstance(gold, dict) else {}
    matches = []
    for pg, regions in pages.items():
        for region in regions or []:
            if isinstance(region, dict) and region.get("id") == rid:
                matches.append((int(pg), region))
    if len(matches) > 1 and raise_ambiguous:
        pages = sorted({page for page, _ in matches})
        raise AmbiguousRegionError(
            f"region id {rid!r} is ambiguous on pages {pages} of {slug!r}; "
            f"qualify the page, e.g. 'p{pages[0]}/{rid}'",
            region_id=rid, pages=pages,
        )
    return matches[0] if len(matches) == 1 else None


async def _source_ref(
    store: DocStore, slug: str, page: int, region: dict[str, Any]
) -> dict[str, Any]:
    """Build provenance from the resolved page and the same pinned index.

    Nested caller citations are not a second region locator. Legacy records
    without canonical geometry/identity keep those fields unavailable.
    """
    source = {
        "coord_origin": region.get("coord_origin", "top-left"),
        "slug": slug,
        "page": page,
        "region_id": region.get("id"),
        "bbox": region.get("bbox") or region.get("approx_bbox"),
    }
    document = (await store.get_index(slug) or {}).get("document", {})
    for key, value in (
        ("source_sha256", (document.get("source") or {}).get("sha256")),
        ("generation_id", (document.get("generation") or {}).get("id")),
    ):
        if value is not None:
            source[key] = value
    return source


_STANDARD_REGION_KEYS = frozenset(
    {
        "id", "kind", "title", "description", "page", "bbox", "approx_bbox",
        "tags", "entities", "geometry", "member_item_ids", "table_slice",
        "cells", "content", "source_ref", "derived_from",
    }
)


def _producer_payload(region: dict[str, Any]) -> dict[str, Any] | None:
    """Keys outside the standard region schema (an OIP producer's payload,
    e.g. a chart digitizer's ``series``/``axes``) — returned verbatim so the
    read view never hides stored data."""
    extra = {k: v for k, v in region.items() if k not in _STANDARD_REGION_KEYS}
    return extra or None


async def _members(
    store: DocStore, slug: str, page: int, region: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Expand ``member_item_ids`` into the silver items they name, so a
    caller can cite the precise evidence without a second round trip."""
    member_ids = region.get("member_item_ids")
    if not member_ids:
        return None
    candidates = await store.get_page_candidates(slug, page) or []
    by_id = {c.get("id"): c for c in candidates if isinstance(c, dict)}
    out: list[dict[str, Any]] = []
    for m in member_ids:
        item = by_id.get(m)
        if item is None:
            continue
        out.append(
            {
                "item_id": m,
                "kind": item.get("label") or item.get("kind"),
                "bbox": item.get("bbox"),
                "text": (item.get("text") or "")[:120],
            }
        )
    return out or None


async def inspect_region(
    store: DocStore, slug: str, region_id: str, *, raise_ambiguous: bool = False
) -> dict[str, Any] | None:
    """Return one gold region's full record + a grounding `source_ref`."""
    store = store.snapshot(slug)
    found = await find_region(store, slug, region_id, raise_ambiguous=raise_ambiguous)
    if found is None:
        return None
    page, region = found
    return {
        "slug": slug,
        "page": page,
        "region_id": region.get("id"),
        "kind": region.get("kind"),
        "title": region.get("title"),
        "description": region.get("description"),
        "bbox": region.get("bbox") or region.get("approx_bbox"),
        "tags": region.get("tags", []),
        "entities": region.get("entities", []),
        "geometry": region.get("geometry"),
        "member_item_ids": region.get("member_item_ids"),
        "members": await _members(store, slug, page, region),
        "table_slice": region.get("table_slice"),
        "cells": region.get("cells"),
        "table_topology": topology_status(region) if region.get("cells") else None,
        "content": region.get("content"),
        "derived_from": region.get("derived_from"),
        "stored_source_ref": region.get("source_ref"),
        "data": _producer_payload(region),
        "source_ref": await _source_ref(store, slug, page, region),
    }


async def get_region_content(
    store: DocStore, slug: str, region_id: str, *, raise_ambiguous: bool = False
) -> dict[str, Any] | None:
    """Return one gold region's reconstructed content (markdown + cells).

    Prefers the region's stored `content`; when absent (e.g. a region whose
    bbox snapped to nothing), rebuilds it from the page's silver candidates via
    `member_item_ids`."""
    store = store.snapshot(slug)
    found = await find_region(store, slug, region_id, raise_ambiguous=raise_ambiguous)
    if found is None:
        return None
    page, region = found
    content = region.get("content")
    if not (isinstance(content, str) and content.strip()):
        member_ids = region.get("member_item_ids")
        if member_ids:
            candidates = await store.get_page_candidates(slug, page) or []
            by_id = {
                c.get("id"): c for c in candidates if isinstance(c, dict)
            }
            items = [by_id[m] for m in member_ids if m in by_id]
            if items:
                content = region_content_from_items(items)
    return {
        "slug": slug,
        "page": page,
        "region_id": region.get("id"),
        "kind": region.get("kind"),
        "content": content or "",
        "cells": region.get("cells"),
        "derived_from": region.get("derived_from"),
        "stored_source_ref": region.get("source_ref"),
        "data": _producer_payload(region),
        "table_topology": topology_status(region) if region.get("cells") else None,
        "source_ref": await _source_ref(store, slug, page, region),
    }
