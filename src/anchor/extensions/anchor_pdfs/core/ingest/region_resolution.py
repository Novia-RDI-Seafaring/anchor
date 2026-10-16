"""Resolve harness-submitted regions against trusted silver candidates.

The interface is deliberately small: callers provide untrusted region dicts,
one page number, and that page's persisted candidates. The module returns
either fully resolved gold regions or structured repair errors.
"""

from __future__ import annotations

from typing import Any

from anchor.extensions.anchor_pdfs.core.ingest.geometry import (
    BLOCK_KINDS,
    EXCLUSIVE_LABELS,
    PICTURE_KINDS,
    adopt_table,
    disown_shared_members,
    in_page_points,
    keep_in_table,
    keep_picture_items,
    merge_into_pictures,
    merged_region,
    mostly_inside,
    needs_adoption,
    outside_tables,
    picture_frames,
)
from anchor.extensions.anchor_pdfs.core.ingest.validation import (
    REGION_KINDS,
    bbox_error,
    region_id_errors,
    validate_region,
)
from anchor.extensions.anchor_pdfs.core.silver import (
    region_content_from_items,
    render_table_cells_md,
    snap_to_docling_items,
    table_bbox_from_items,
    table_data_from_items,
    union_bbox,
)
from anchor.extensions.anchor_pdfs.core.table_topology import select_table_cells, topology_status

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


def source_region_metadata(region: dict[str, Any]) -> dict[str, Any]:
    """Persist original chunks as metadata; producer payloads stay authoritative."""
    if region.get("derived_from"):
        return dict(region)
    return {key: value for key, value in region.items()
            if key not in {"content", "cells", "table_topology"}}


def materialize_source_region(
    region: dict[str, Any], *, page: int, items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconstruct source content and precise cells from one pinned silver page.

    Legacy callers without full silver keep their stored data. Callers with
    full silver never trust duplicated source content. Derived records bypass
    reconstruction because their payload was created by a separate producer.
    """
    if region.get("derived_from"):
        return dict(region)
    out = source_region_metadata(region)
    if any(not isinstance(item.get("id"), str) for item in items):
        raise ValueError(f"invalid silver item identity on page {page}")
    by_id = {item["id"]: item for item in items}
    if region.get("table_slice") is not None:
        _, bbox, data, content, _, errors = _resolve_table_slice(
            region["table_slice"], index=0, kind=region.get("kind"), by_id=by_id,
        )
        if errors:
            raise ValueError("invalid silver table membership: " + "; ".join(e["message"] for e in errors))
        out.update(data)
        out["bbox"] = bbox
    else:
        member_ids = region.get("member_item_ids")
        if member_ids:
            if not isinstance(member_ids, list) or any(not isinstance(m, str) or m not in by_id for m in member_ids):
                raise ValueError(f"unknown silver members for region {region.get('id')!r} on page {page}")
            selected = [by_id[m] for m in member_ids]
        else:
            bbox = region.get("approx_bbox") or region.get("bbox") or []
            _, indexes = snap_to_docling_items({"items": items}, page, bbox)
            selected = [items[i] for i in indexes]
        content = region_content_from_items(selected, max_chars=None)
        if region.get("kind") in {"table", "spec_block"}:
            out.update(table_data_from_items(selected, region_bbox=region.get("bbox")))
    if content:
        out["content"] = content
    return out


def resolve_regions(
    regions: Any,
    *,
    page: int,
    candidates: list[dict[str, Any]],
    page_size: list[float] | tuple[float, float] | None = None,
    dpi: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve untrusted submissions into validated, grounded gold regions.

    ``page_size`` (points) and ``dpi`` (of the page raster the harness saw)
    let an ``approx_bbox`` be checked against the page: pixels that fit the
    raster are scaled to points, anything outside both is rejected.
    """
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
    resolved_indexes: list[int] = []
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

        geometry, bbox, table_data, content, normalized, geometry_errors = (
            _resolve_geometry(
                index=index,
                kind=raw.get("kind"),
                page=page,
                by_id=by_id,
                docling_view=docling_view,
                member_ids=member_ids,
                approx_bbox=approx_bbox,
                table_slice=table_slice,
                page_size=page_size,
                dpi=dpi,
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
        if table_data and region.get("kind") in {"table", "spec_block"}:
            region.update(table_data)

        shape_errors = validate_region(region, index=index)
        if shape_errors:
            errors.extend(shape_errors)
            continue
        if not geometry or geometry_errors:
            continue
        resolved.append(region)
        resolved_indexes.append(index)

    errors.extend(region_id_errors(resolved, page=page))
    errors.extend(_shared_block_errors(resolved, resolved_indexes, by_id))
    if errors:
        return [], errors
    # The key owns its letters: a picture region named by both gives them up.
    for pos, kept in disown_shared_members(resolved).items():
        kept_items = [by_id[m] for m in kept if m in by_id]
        frame = union_bbox([list(item.get("bbox") or []) for item in kept_items])
        if not frame:
            continue
        region = {**resolved[pos], "member_item_ids": kept, "bbox": frame}
        content = region_content_from_items(kept_items)
        if content:
            region["content"] = content
        else:
            region.pop("content", None)
        resolved[pos] = region

    # One drawing in the PDF is one region: picture regions take their
    # Docling picture's frame, and views of one drawing merge.
    pictures = [
        box for candidate in by_id.values()
        if candidate.get("label") == "picture" and (box := _candidate_bbox(candidate))
    ]
    frames, absorbed = merge_into_pictures(resolved, pictures)
    for pos, frame in frames.items():
        region = merged_region(resolved[pos], [resolved[o] for o in absorbed.get(pos, [])])
        region["bbox"] = frame
        content = region_content_from_items([by_id[m] for m in region.get("member_item_ids") or [] if m in by_id])
        if content:
            region["content"] = content
        resolved[pos] = region
    gone = {o for others in absorbed.values() for o in others}
    resolved = [r for pos, r in enumerate(resolved) if pos not in gone]

    # A picture that spans a drawing and the key beside it gives the key
    # its own room (see ``ingest.geometry.picture_frames``).
    own_boxes = {
        pos: [
            box for member in region.get("member_item_ids") or []
            if member in by_id
            and by_id[member].get("label") != "picture"
            and (box := _candidate_bbox(by_id[member]))
        ]
        for pos, region in enumerate(resolved)
        if region.get("kind") in PICTURE_KINDS
    }
    for pos, frame in picture_frames(resolved, own_boxes).items():
        region = resolved[pos]
        kept = [
            member for member in region.get("member_item_ids") or []
            if member in by_id and (
                by_id[member].get("label") == "picture"
                or mostly_inside(_candidate_bbox(by_id[member]), frame)
            )
        ]
        region = {**region, "bbox": frame, "member_item_ids": kept}
        content = region_content_from_items([by_id[m] for m in kept])
        if content:
            region["content"] = content
        else:
            region.pop("content", None)
        resolved[pos] = region
    return resolved, []


def _candidate_bbox(candidate: dict[str, Any]) -> list[float] | None:
    raw = candidate.get("bbox")
    if isinstance(raw, list) and len(raw) == 4:
        try:
            return [float(v) for v in raw]
        except (TypeError, ValueError):
            return None
    return None


def _shared_block_errors(
    resolved: list[dict[str, Any]],
    indexes: list[int],
    by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """One table or picture, one region. Names every region that shares one.

    Two regions naming the same table are two regions for one block: a sign
    the member lists ran past their block. This path has a repair round, so
    the page goes back with the item and the regions named.
    """
    holders: dict[str, list[tuple[int, str]]] = {}
    for index, region in zip(indexes, resolved, strict=True):
        for member_id in region.get("member_item_ids") or []:
            label = (by_id.get(member_id) or {}).get("label")
            if label in EXCLUSIVE_LABELS:
                holders.setdefault(member_id, []).append((index, str(region.get("id"))))
    errors: list[dict[str, Any]] = []
    for member_id, owners in holders.items():
        if len(owners) < 2:
            continue
        label = by_id[member_id]["label"]
        names = ", ".join(region_id for _, region_id in owners)
        for index, _ in owners:
            errors.append(_err(
                index,
                "member_item_ids",
                f"{member_id} is a {label} named by regions {names}; a {label} is "
                "one block and belongs to one region. Keep it in the region whose "
                "body it is and name only that block's own items in the others "
                "(or use table_slice for one part of a table).",
            ))
    return errors


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
    page_size: list[float] | tuple[float, float] | None = None,
    dpi: int | None = None,
) -> tuple[
    str,
    list[float],
    dict[str, Any],
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
            kind=kind,
            page=page,
            by_id=by_id,
        )
    return _resolve_approx_bbox(
        approx_bbox,
        index=index,
        kind=kind,
        page=page,
        docling_view=docling_view,
        page_size=page_size,
        dpi=dpi,
    )


def _resolve_members(
    member_ids: Any,
    *,
    index: int,
    page: int,
    by_id: dict[str, dict[str, Any]],
    kind: Any = None,
) -> tuple[str, list[float], dict[str, Any], str, Any, list[dict[str, Any]]]:
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
    kept_ids = list(member_ids)
    if kind in PICTURE_KINDS:
        # A picture region is its picture and the labels inside it, not the
        # table a run-on member list dragged along.
        kept = keep_picture_items(selected_items)
        selected_items = [selected_items[pos] for pos in kept]
        kept_ids = [kept_ids[pos] for pos in kept]
    elif kind in BLOCK_KINDS:
        # Named by heading and cell texts, which can stand in other tables
        # too, or with another table than its heading's: take the table
        # under the heading and what is inside it.
        tables = [(cid, c) for cid, c in by_id.items() if c.get("label") == "table"]
        table_items = [c for _, c in tables]
        chosen = (
            adopt_table(selected_items, table_items)
            if needs_adoption(selected_items, table_items) else None
        )
        if chosen is not None:
            table_id, table = tables[chosen]
            kept = keep_in_table(selected_items, _candidate_bbox(table) or [])
            kept_ids = [table_id, *(
                kept_ids[pos] for pos in kept
                if kept_ids[pos] != table_id and selected_items[pos].get("label") != "table"
            )]
            selected_items = [by_id[cid] for cid in kept_ids]
        elif not any(item.get("label") == "table" for item in selected_items):
            outside = outside_tables(selected_items, table_items)
            if outside:
                kept_ids = [kept_ids[pos] for pos in outside]
                selected_items = [selected_items[pos] for pos in outside]
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
        table_data_from_items(selected_items),
        region_content_from_items(selected_items),
        kept_ids,
        [],
    )


def _resolve_approx_bbox(
    approx_bbox: Any,
    *,
    index: int,
    kind: Any,
    page: int,
    docling_view: dict[str, list[dict[str, Any]]],
    page_size: list[float] | tuple[float, float] | None = None,
    dpi: int | None = None,
) -> tuple[str, list[float], dict[str, Any], str, Any, list[dict[str, Any]]]:
    message = bbox_error(approx_bbox)
    if message:
        return _failed_geometry(_err(index, "approx_bbox", message))
    normalized = [float(value) for value in approx_bbox]
    if page_size and len(page_size) == 2:
        normalized, message = in_page_points(normalized, page_size, dpi)
        if message:
            return _failed_geometry(_err(index, "approx_bbox", f"approx_{message}"))
    snapped, item_indexes = snap_to_docling_items(docling_view, page, normalized)
    if not snapped:
        return "coarse", normalized, {}, "", normalized, []

    items = docling_view["items"]
    table_data = table_data_from_items(items, item_indexes, region_bbox=normalized)
    content = region_content_from_items(items, item_indexes)
    if kind == "table":
        table_bbox = table_bbox_from_items(
            items,
            item_indexes,
            region_bbox=normalized,
        )
        if table_bbox:
            snapped = table_bbox
    return "snapped", snapped, table_data, content, normalized, []


def _resolve_table_slice(
    selector: Any,
    *,
    index: int,
    kind: Any,
    by_id: dict[str, dict[str, Any]],
) -> tuple[str, list[float], dict[str, Any], str, Any, list[dict[str, Any]]]:
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
    table_data = table_data_from_items([candidate])
    cells = table_data.get("cells", [])
    if not cells:
        return _failed_geometry(_err(
            index,
            "table_slice.candidate_id",
            "the selected table candidate has no addressable cells",
        ))
    if topology_status(table_data)["status"] not in {"valid", "reconciled"}:
        return _failed_geometry(_err(
            index, "table_slice", "table topology is unverified; re-ingest or select the whole candidate for inspection",
        ))

    rows, row_error = _indexes(
        selector.get("rows"),
        available={r for cell in cells for r in range(cell["row"], cell.get("row_end", cell["row"] + 1))},
        field="table_slice.rows",
        required=True,
    )
    columns, column_error = _indexes(
        selector.get("columns"),
        available={c for cell in cells for c in range(cell["col"], cell.get("col_end", cell["col"] + 1))},
        field="table_slice.columns",
        required=False,
    )
    errors = [
        _err(index, field, message)
        for field, message in (row_error, column_error)
        if field
    ]
    if errors:
        return "", [], {}, "", None, errors

    selected = [
        cell
        for cell in cells
        if set(range(cell["row"], cell.get("row_end", cell["row"] + 1))).intersection(rows)
        and (not columns or set(range(cell["col"], cell.get("col_end", cell["col"] + 1))).intersection(columns))
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
    # A slice may include an entire merged cell, never a fabricated fragment.
    # Pair projection preserves the full-table decision even if the caller
    # selects just two columns from a previously ambiguous multicolumn row.
    selected_data = select_table_cells(table_data, selected)
    return (
        "table_slice",
        bbox,
        selected_data,
        render_table_cells_md(selected, selected_data.get("table_topology")),
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
) -> tuple[str, list[float], dict[str, Any], str, Any, list[dict[str, Any]]]:
    return "", [], {}, "", None, [error]


def _err(index: int, field: str, message: str) -> dict[str, Any]:
    return {"region_index": index, "field": field, "message": message}
