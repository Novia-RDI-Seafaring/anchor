"""Attach value-cell bboxes to spec-row source refs when gold cells exist."""
from __future__ import annotations

from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore


async def enrich_spec_row_source_refs(data: Any, store: DocStore) -> Any:
    if not isinstance(data, dict):
        return data
    rows = data.get("rows")
    if not isinstance(rows, list):
        return data

    cache: dict[tuple[str, int], list[dict[str, Any]]] = {}
    next_rows: list[Any] = []
    changed = False
    node_ref = data.get("source_ref") if isinstance(data.get("source_ref"), dict) else {}
    node_slug = data.get("source_doc_slug") if isinstance(data.get("source_doc_slug"), str) else None
    node_region_id = data.get("source_region_id") if isinstance(data.get("source_region_id"), str) else None

    for row in rows:
        if not isinstance(row, dict):
            next_rows.append(row)
            continue
        source_ref = row.get("source_ref") if isinstance(row.get("source_ref"), dict) else {}
        value = row.get("value")
        if not isinstance(value, str) or not value.strip():
            next_rows.append(row)
            continue

        slug = _first_str(source_ref.get("slug"), node_slug, node_ref.get("slug"))
        page = _first_int(source_ref.get("page"), node_ref.get("page"))
        if not slug or page is None:
            next_rows.append(row)
            continue

        regions = await _regions_for_page(store, cache, slug, page)
        region_id = _first_str(
            source_ref.get("region_id"),
            row.get("source_region_id"),
            node_region_id,
            node_ref.get("region_id"),
        )
        region = _find_region(regions, region_id)
        if region is None:
            next_rows.append(row)
            continue

        cell_bbox = _match_value_cell_bbox(region.get("cells"), row.get("key"), value)
        if not cell_bbox:
            next_rows.append(row)
            continue

        new_ref = {**source_ref, "slug": slug, "page": page, "bbox": cell_bbox}
        if region_id:
            new_ref["region_id"] = region_id
        next_rows.append({**row, "source_ref": new_ref})
        changed = True

    return {**data, "rows": next_rows} if changed else data


async def _regions_for_page(
    store: DocStore,
    cache: dict[tuple[str, int], list[dict[str, Any]]],
    slug: str,
    page: int,
) -> list[dict[str, Any]]:
    key = (slug, page)
    if key not in cache:
        payload = await store.get_regions(slug, page=page)
        pages = payload.get("pages", {}) if isinstance(payload, dict) else {}
        cache[key] = pages.get(page) or pages.get(str(page)) or []
    return cache[key]


def _find_region(regions: list[dict[str, Any]], region_id: str | None) -> dict[str, Any] | None:
    if region_id:
        for region in regions:
            if isinstance(region, dict) and region.get("id") == region_id:
                return region
    for region in regions:
        if isinstance(region, dict) and isinstance(region.get("cells"), list):
            return region
    return None


def _match_value_cell_bbox(cells: Any, key: Any, value: str) -> list[float]:
    if not isinstance(cells, list):
        return []
    value_norm = _norm(value)
    if not value_norm:
        return []
    value_cells = [
        cell for cell in cells
        if isinstance(cell, dict) and _norm(cell.get("text")) == value_norm and _clean_bbox(cell.get("bbox"))
    ]
    if not value_cells:
        return []

    key_norm = _norm(key)
    if key_norm:
        keyed = []
        for cell in value_cells:
            row_no = cell.get("row")
            if not isinstance(row_no, int):
                continue
            row_cells = [c for c in cells if isinstance(c, dict) and c.get("row") == row_no]
            if any(_norm(c.get("text")) == key_norm for c in row_cells):
                keyed.append(cell)
        if len(keyed) == 1:
            return _clean_bbox(keyed[0].get("bbox"))

    if len(value_cells) == 1:
        return _clean_bbox(value_cells[0].get("bbox"))
    return []


def _norm(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def _clean_bbox(bbox: Any) -> list[float]:
    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
        return [float(v) for v in bbox]
    return []


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return None
