"""Resolve harness-submitted regions against trusted silver candidates.

The interface is deliberately small: callers provide untrusted region dicts,
one page number, and that page's persisted candidates. The module returns
either fully resolved gold regions or structured repair errors.
"""

from __future__ import annotations

from typing import Any

from anchor.extensions.anchor_pdfs.core.ingest.validation import (
    REGION_KINDS,
    bbox_error,
    validate_region,
)
from anchor.extensions.anchor_pdfs.core.silver import (
    region_content_from_items,
    render_table_cells_md,
    snap_to_docling_items,
    table_bbox_from_items,
    table_cells_from_items,
    union_bbox,
)

_SUBMIT_REGION_FIELDS = frozenset({
    "id",
    "kind",
    "title",
    "description",
    "member_item_ids",
    "approx_bbox",
    "table_slice",
    "tags",
    "entities",
})
_TABLE_SLICE_FIELDS = frozenset({"candidate_id", "rows", "columns"})

PAGE_INSTRUCTIONS = (
    "Read the page image (image.path or base64) alongside raw_md. "
    "1) If needs_polish, rewrite raw_md into faithful markdown for this page: "
    "fix reading order, reconstruct tables, transcribe values exactly; never "
    "invent content that is not on the page. "
    "2) List the meaningful regions: for each, pick kind "
    f"({'|'.join(REGION_KINDS)}), a short title, a 1-2 sentence description, "
    "and name its geometry by listing the candidate item ids it covers in "
    "member_item_ids (the server computes the bbox from those). For one logical "
    "part of a table, use table_slice {candidate_id, rows, columns?}; row and "
    "column indexes come from the candidate cells, and the server computes "
    "cell-level content and geometry. Only when no candidate covers a visual, "
    "send approx_bbox [left, top, right, bottom] in top-left PDF points (y down) "
    "instead. Optional: tags[], entities[] (product/model identifiers). For "
    "table/spec_block regions, split visual sub-tables and repeat duplicate "
    "values for each key instead of deduplicating them. "
    "3) Submit with ingest_submit_page; on a rejection, repair the named "
    "fields and resubmit (resubmitting a page replaces it)."
)


def resolve_regions(
    regions: Any,
    *,
    page: int,
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve untrusted submissions into validated, grounded gold regions."""
    if not isinstance(regions, list):
        return [], [_err(0, "regions", "regions must be a list")]

    by_id = {
        candidate.get("id"): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and isinstance(candidate.get("id"), str)
    }
    docling_view = {
        "items": [{**candidate, "page": page} for candidate in by_id.values()]
    }
    resolved: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for index, raw in enumerate(regions):
        if not isinstance(raw, dict):
            errors.append(_err(index, "", "region must be an object"))
            continue
        unknown = sorted(set(raw) - _SUBMIT_REGION_FIELDS)
        if unknown:
            errors.append(_err(
                index,
                ",".join(unknown),
                f"unknown fields {unknown}; allowed: {sorted(_SUBMIT_REGION_FIELDS)}",
            ))
            continue

        member_ids = raw.get("member_item_ids")
        approx_bbox = raw.get("approx_bbox")
        table_slice = raw.get("table_slice")
        selector_count = sum((
            member_ids is not None,
            approx_bbox is not None,
            table_slice is not None,
        ))
        if selector_count != 1:
            errors.append(_err(
                index,
                "geometry",
                "region needs exactly one geometry selector: member_item_ids, "
                "table_slice, or approx_bbox",
            ))
            errors.extend(validate_region(
                _region_payload(raw, index=index, page=page),
                index=index,
            ))
            continue

        geometry, bbox, cells, content, normalized, geometry_errors = (
            _resolve_geometry(
                index=index,
                kind=raw.get("kind"),
                page=page,
                by_id=by_id,
                docling_view=docling_view,
                member_ids=member_ids,
                approx_bbox=approx_bbox,
                table_slice=table_slice,
            )
        )
        if geometry_errors:
            errors.extend(geometry_errors)

        region = _region_payload(
            raw,
            index=index,
            page=page,
            bbox=bbox,
            geometry=geometry,
        )
        if geometry == "members":
            region["member_item_ids"] = normalized
        elif geometry in {"snapped", "coarse"}:
            region["approx_bbox"] = normalized
        elif geometry == "table_slice":
            region["table_slice"] = normalized
        if content:
            region["content"] = content
        if cells and region.get("kind") in {"table", "spec_block"}:
            region["cells"] = cells

        shape_errors = validate_region(region, index=index)
        if shape_errors:
            errors.extend(shape_errors)
            continue
        if not geometry or geometry_errors:
            continue
        resolved.append(region)

    _reject_duplicate_ids(resolved, errors, page=page)
    if errors:
        return [], errors
    return resolved, []


def _region_payload(
    raw: dict[str, Any],
    *,
    index: int,
    page: int,
    bbox: list[float] | None = None,
    geometry: str = "",
) -> dict[str, Any]:
    """Build the shared validation payload, including on geometry failures."""
    return {
        "id": raw.get("id") or f"r{index + 1}",
        "kind": raw.get("kind"),
        "title": raw.get("title"),
        "description": raw.get("description") or "",
        "page": page,
        "bbox": bbox or [0.0, 0.0, 0.0, 0.0],
        "geometry": geometry,
        "tags": raw.get("tags") or [],
        "entities": raw.get("entities") or [],
    }


def _resolve_geometry(
    *,
    index: int,
    kind: Any,
    page: int,
    by_id: dict[str, dict[str, Any]],
    docling_view: dict[str, list[dict[str, Any]]],
    member_ids: Any,
    approx_bbox: Any,
    table_slice: Any,
) -> tuple[
    str,
    list[float],
    list[dict[str, Any]],
    str,
    Any,
    list[dict[str, Any]],
]:
    if table_slice is not None:
        return _resolve_table_slice(
            table_slice,
            index=index,
            kind=kind,
            by_id=by_id,
        )
    if member_ids is not None:
        return _resolve_members(
            member_ids,
            index=index,
            page=page,
            by_id=by_id,
        )
    return _resolve_approx_bbox(
        approx_bbox,
        index=index,
        kind=kind,
        page=page,
        docling_view=docling_view,
    )


def _resolve_members(
    member_ids: Any,
    *,
    index: int,
    page: int,
    by_id: dict[str, dict[str, Any]],
) -> tuple[str, list[float], list[dict[str, Any]], str, Any, list[dict[str, Any]]]:
    if not isinstance(member_ids, list) or not member_ids:
        return _failed_geometry(
            _err(index, "member_item_ids", "member_item_ids must be a non-empty list")
        )
    if not all(isinstance(member_id, str) for member_id in member_ids):
        return _failed_geometry(
            _err(index, "member_item_ids", "member_item_ids must contain only strings")
        )
    missing = [member_id for member_id in member_ids if member_id not in by_id]
    if missing:
        return _failed_geometry(_err(
            index,
            "member_item_ids",
            f"unknown candidate ids on page {page}: {missing}",
        ))

    selected_items = [by_id[member_id] for member_id in member_ids]
    bbox = union_bbox([list(item.get("bbox") or []) for item in selected_items])
    if not bbox:
        return _failed_geometry(_err(
            index,
            "member_item_ids",
            "named candidates have no usable bboxes; send approx_bbox instead",
        ))
    return (
        "members",
        bbox,
        table_cells_from_items(selected_items),
        region_content_from_items(selected_items),
        list(member_ids),
        [],
    )


def _resolve_approx_bbox(
    approx_bbox: Any,
    *,
    index: int,
    kind: Any,
    page: int,
    docling_view: dict[str, list[dict[str, Any]]],
) -> tuple[str, list[float], list[dict[str, Any]], str, Any, list[dict[str, Any]]]:
    message = bbox_error(approx_bbox)
    if message:
        return _failed_geometry(_err(index, "approx_bbox", message))
    normalized = [float(value) for value in approx_bbox]
    snapped, item_indexes = snap_to_docling_items(docling_view, page, normalized)
    if not snapped:
        return "coarse", normalized, [], "", normalized, []

    items = docling_view["items"]
    cells = table_cells_from_items(items, item_indexes, region_bbox=normalized)
    content = region_content_from_items(items, item_indexes)
    if kind == "table":
        table_bbox = table_bbox_from_items(
            items,
            item_indexes,
            region_bbox=normalized,
        )
        if table_bbox:
            snapped = table_bbox
    return "snapped", snapped, cells, content, normalized, []


def _resolve_table_slice(
    selector: Any,
    *,
    index: int,
    kind: Any,
    by_id: dict[str, dict[str, Any]],
) -> tuple[str, list[float], list[dict[str, Any]], str, Any, list[dict[str, Any]]]:
    if not isinstance(selector, dict):
        return _failed_geometry(
            _err(index, "table_slice", "table_slice must be an object")
        )
    unknown = sorted(set(selector) - _TABLE_SLICE_FIELDS)
    if unknown:
        return _failed_geometry(_err(
            index,
            "table_slice",
            f"unknown table_slice fields {unknown}; allowed: {sorted(_TABLE_SLICE_FIELDS)}",
        ))
    if kind not in {"table", "spec_block"}:
        return _failed_geometry(_err(
            index,
            "table_slice",
            "table_slice is only valid for table or spec_block regions",
        ))

    candidate_id = selector.get("candidate_id")
    candidate = by_id.get(candidate_id) if isinstance(candidate_id, str) else None
    if candidate is None or candidate.get("label") != "table":
        return _failed_geometry(_err(
            index,
            "table_slice.candidate_id",
            "candidate_id must name a table candidate on this page",
        ))
    cells = table_cells_from_items([candidate])
    if not cells:
        return _failed_geometry(_err(
            index,
            "table_slice.candidate_id",
            "the selected table candidate has no addressable cells",
        ))

    rows, row_error = _indexes(
        selector.get("rows"),
        available={cell["row"] for cell in cells},
        field="table_slice.rows",
        required=True,
    )
    columns, column_error = _indexes(
        selector.get("columns"),
        available={cell["col"] for cell in cells},
        field="table_slice.columns",
        required=False,
    )
    errors = [
        _err(index, field, message)
        for field, message in (row_error, column_error)
        if field
    ]
    if errors:
        return "", [], [], "", None, errors

    selected = [
        cell
        for cell in cells
        if cell["row"] in rows and (not columns or cell["col"] in columns)
    ]
    bbox = union_bbox([list(cell.get("bbox") or []) for cell in selected])
    if not selected or not bbox:
        return _failed_geometry(_err(
            index,
            "table_slice",
            "selected table cells have no usable content and bboxes",
        ))
    normalized = {"candidate_id": candidate_id, "rows": rows}
    if columns:
        normalized["columns"] = columns
    return (
        "table_slice",
        bbox,
        selected,
        render_table_cells_md(selected),
        normalized,
        [],
    )


def _indexes(
    value: Any,
    *,
    available: set[int],
    field: str,
    required: bool,
) -> tuple[list[int], tuple[str, str]]:
    if value is None and not required:
        return [], ("", "")
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    ):
        return [], (field, f"{field} must be a non-empty list of integers")
    if len(set(value)) != len(value):
        return [], (field, f"{field} must not contain duplicates")
    unknown = sorted(set(value) - available)
    if unknown:
        noun = "rows" if field.endswith("rows") else "columns"
        return [], (field, f"unknown {noun} for the selected table: {unknown}")
    return sorted(value), ("", "")


def _failed_geometry(
    error: dict[str, Any],
) -> tuple[str, list[float], list[dict[str, Any]], str, Any, list[dict[str, Any]]]:
    return "", [], [], "", None, [error]


def _reject_duplicate_ids(
    regions: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    *,
    page: int,
) -> None:
    seen: set[str] = set()
    for index, region in enumerate(regions):
        region_id = region["id"]
        if region_id in seen:
            errors.append(_err(
                index,
                "id",
                f"duplicate region id {region_id!r} on page {page}",
            ))
        seen.add(region_id)


def _err(index: int, field: str, message: str) -> dict[str, Any]:
    return {"region_index": index, "field": field, "message": message}
