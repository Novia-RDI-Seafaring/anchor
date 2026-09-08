"""Resolve a ``source_ref`` to the most precise stored evidence (#242 P2b).

A ref may carry optional selectors beyond the region: ``item_id`` (one
silver item, ``p<page>-i<n>``) and ``cell`` (``{row, col}`` of a table).
Resolution precedence is cell > item > region > bbox; the answer reports
which layer resolved (``precision``) so callers — the viewer's highlight,
an agent citing evidence — can trust the bbox they get. A ref that names
a selector whose geometry is not stored falls through to the next layer
rather than failing, so legacy refs resolve exactly as before.
"""
from __future__ import annotations

import re
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.region_inspect import find_region
from anchor.extensions.anchor_pdfs.core.silver import table_cells_from_items

_ITEM_ID = re.compile(r"^p(\d+)-i\d+$")


def _bbox(value: Any) -> list[float] | None:
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(v, (int, float)) for v in value)
    ):
        return [float(v) for v in value]
    return None


async def resolve_source_ref(
    store: DocStore, slug: str, ref: dict[str, Any]
) -> dict[str, Any] | None:
    """Return ``{slug, page, bbox, precision, ...selectors}`` or None.

    ``ref.slug`` wins over the ``slug`` argument. Page is taken from the
    ref, parsed from ``item_id``, or found via the region id.
    """
    slug = ref.get("slug") or slug
    page = ref.get("page") if isinstance(ref.get("page"), int) else None
    region_id = ref.get("region_id") if isinstance(ref.get("region_id"), str) else None
    item_id = ref.get("item_id") if isinstance(ref.get("item_id"), str) else None
    cell = ref.get("cell") if isinstance(ref.get("cell"), dict) else None

    if page is None and item_id:
        m = _ITEM_ID.match(item_id)
        if m:
            page = int(m.group(1))

    region: dict[str, Any] | None = None
    if region_id:
        token = f"p{page}/{region_id}" if page is not None else region_id
        found = await find_region(store, slug, token)
        if found is not None:
            page, region = found

    if page is None:
        # A bare bbox ref still answers, page unknown refs cannot.
        return None

    def _answer(bbox: list[float], precision: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "slug": slug,
            "page": page,
            "bbox": bbox,
            "precision": precision,
        }
        if region_id:
            out["region_id"] = region_id
        if item_id and precision == "item":
            out["item_id"] = item_id
        if cell and precision == "cell":
            out["cell"] = {"row": cell.get("row"), "col": cell.get("col")}
        return out

    if cell is not None:
        bbox = await _cell_bbox(store, slug, page, region, cell)
        if bbox is not None:
            return _answer(bbox, "cell")

    if item_id:
        candidates = await store.get_page_candidates(slug, page) or []
        for c in candidates:
            if isinstance(c, dict) and c.get("id") == item_id:
                bbox = _bbox(c.get("bbox"))
                if bbox is not None:
                    return _answer(bbox, "item")
                break

    if region is not None:
        bbox = _bbox(region.get("bbox")) or _bbox(region.get("approx_bbox"))
        if bbox is not None:
            return _answer(bbox, "region")

    bbox = _bbox(ref.get("bbox"))
    if bbox is not None:
        return _answer(bbox, "bbox")
    return None


async def _cell_bbox(
    store: DocStore,
    slug: str,
    page: int,
    region: dict[str, Any] | None,
    cell: dict[str, Any],
) -> list[float] | None:
    row, col = cell.get("row"), cell.get("col")
    if not isinstance(row, int) or not isinstance(col, int):
        return None

    def pick(cells: Any) -> list[float] | None:
        for c in cells or []:
            if (
                isinstance(c, dict)
                and c.get("row") == row
                and c.get("col") == col
            ):
                return _bbox(c.get("bbox"))
        return None

    if region is not None:
        bbox = pick(region.get("cells"))
        if bbox is not None:
            return bbox
    # Fall back to the silver table geometry (#270 stores per-cell bboxes).
    candidates = await store.get_page_candidates(slug, page) or []
    region_bbox = _bbox(region.get("bbox")) if region else None
    return pick(table_cells_from_items(candidates, region_bbox=region_bbox))
