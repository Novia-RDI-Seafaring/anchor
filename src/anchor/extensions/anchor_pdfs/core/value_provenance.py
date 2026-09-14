"""Refine spec refs only within their source scope and a certified key/value pair.

Unresolved or contradictory evidence leaves caller data unchanged. A no-op
is not a verified-grounding verdict and never repairs historical references.
"""

from __future__ import annotations

import math
from typing import Any

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.table_topology import validated_pairs


async def enrich_spec_row_source_refs(data: Any, store: DocStore) -> Any:
    if not isinstance(data, dict):
        return data
    rows = data.get("rows")
    if not isinstance(rows, list):
        return data

    cache: dict[tuple[str, int], list[dict[str, Any]]] = {}
    next_rows: list[Any] = []
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            next_rows.append(row)
            continue
        source_ref = row.get("source_ref", {})
        if not isinstance(source_ref, dict):
            next_rows.append(row)
            continue
        value = row.get("value")
        if not isinstance(value, str) or not value.strip():
            next_rows.append(row)
            continue

        scope = _source_scope(data, row, source_ref)
        if scope is None:
            next_rows.append(row)
            continue
        slug, page = scope["slug"], scope["page"]
        region_id = scope.get("region_id")
        regions = await _regions_for_page(store, cache, slug, page)
        candidates = [
            (region, key_cell, value_cell)
            for region in _candidate_regions(regions, region_id, page)
            for key_cell, value_cell in _matching_pairs(region, row.get("key"), value)
        ]
        if len(candidates) != 1:
            next_rows.append(row)
            continue
        region, key_cell, value_cell = candidates[0]
        cell_bbox = _clean_bbox(value_cell.get("bbox"))
        if not cell_bbox or not _locator_agrees(scope, region, key_cell, value_cell):
            next_rows.append(row)
            continue

        new_ref = {
            **source_ref,
            "slug": slug,
            "page": page,
            "bbox": cell_bbox,
            "coord_origin": "top-left",
        }
        # Both boxes describe this matched cell. Do not retain an inherited
        # cell locator from another coordinate space under the new stamp.
        detail = source_ref.get("detail")
        if isinstance(detail, dict) and "cell_bbox" in detail:
            new_ref["detail"] = {**detail, "cell_bbox": cell_bbox}
        if source_ref.get("coord_origin") != "top-left":
            for key in ("approx_bbox", "approximate_bbox"):
                if key in new_ref:
                    new_ref[key] = None
        new_ref["region_id"] = region["id"]
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
        pages = (
            payload.get("pages", {})
            if isinstance(payload, dict) and payload.get("slug", slug) == slug
            else {}
        )
        regions = pages.get(page, pages.get(str(page), [])) if isinstance(pages, dict) else []
        cache[key] = regions if isinstance(regions, list) else []
    return cache[key]


def _candidate_regions(
    regions: list[dict[str, Any]], region_id: str | None, page: int
) -> list[dict[str, Any]]:
    candidates = [region for region in regions if isinstance(region, dict)]
    if region_id is not None:
        candidates = [region for region in candidates if region.get("id") == region_id]
        if len(candidates) != 1:
            return []
    ids = [region.get("id") for region in candidates]
    if any(not isinstance(identity, str) or not identity.strip() for identity in ids):
        return []
    if len(set(ids)) != len(ids):
        return []
    return [
        region
        for region in candidates
        if type(region.get("page", page)) is int and region.get("page", page) == page
    ]


def _matching_pairs(region: dict[str, Any], key: Any, value: str) -> list[tuple[dict, dict]]:
    """Keep G1's directional association intact; never match a value alone."""
    key_norm, value_norm = _norm(key).lower(), _norm(value)
    if not key_norm or not value_norm:
        return []
    return [
        (key_cell, value_cell)
        for key_cell, value_cell in validated_pairs(region)
        if _norm(key_cell.get("text")).lower() == key_norm
        and _norm(value_cell.get("text")) == value_norm
    ]


def _norm(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    # Value case is significant for engineering units (mm != Mm).
    return " ".join(value.strip().split())


def _clean_bbox(bbox: Any) -> list[float]:
    if (
        isinstance(bbox, list)
        and len(bbox) == 4
        and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in bbox
        )
        and bbox[0] < bbox[2]
        and bbox[1] < bbox[3]
    ):
        return [float(v) for v in bbox]
    return []


def _locator_agrees(scope: dict, region: dict, key_cell: dict, value_cell: dict) -> bool:
    detail = scope.get("detail")
    if detail is not None and not isinstance(detail, dict):
        return False
    detail = detail or {}
    if "table_topology" in detail:
        proof = detail["table_topology"]
        verdict = region["table_topology"]
        expected = {
            "digest": verdict["digest"],
            "key_cell_id": key_cell["cell_id"],
            "value_cell_id": value_cell["cell_id"],
        }
        if not isinstance(proof, dict) or any(proof.get(k) != v for k, v in expected.items()):
            return False
        pair = next(
            p
            for p in verdict["pairs"]
            if p["key"] == key_cell["cell_id"] and p["value"] == value_cell["cell_id"]
        )
        expected.update(
            version=verdict["version"],
            status=verdict["status"],
            key_text=key_cell["text"],
            key_bbox=key_cell["bbox"],
            row=key_cell["row"],
            association_basis=pair.get("basis", "validated_row"),
        )
        if any(proof[k] != v for k, v in expected.items() if k in proof):
            return False
    boxes = [box for box in (scope.get("bbox"), detail.get("cell_bbox")) if box is not None]
    origin = scope.get("coord_origin")
    if origin not in (None, "top-left", "bottom-left"):
        return False
    if not boxes:
        return True
    if origin == "bottom-left":
        # R1 compatibility: select new canonical evidence from an explicit
        # source and exact pair, never transform or infer the old geometry.
        return scope.get("region_id") is not None
    if origin != "top-left":
        return False
    cell = value_cell["bbox"]
    for box in boxes:
        if not _clean_bbox(box) or not (
            box[0] - 1e-6 <= cell[0]
            and box[1] - 1e-6 <= cell[1]
            and cell[2] <= box[2] + 1e-6
            and cell[3] <= box[3] + 1e-6
        ):
            return False
    return True


def _inherit_scope(child: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    # A more specific document/page/region may override defaults, but cannot
    # borrow the old source's remaining locator or fine-grained geometry.
    inherited = parent
    for field, retained in (("slug", ()), ("page", ("slug",)), ("region_id", ("slug", "page"))):
        if field in child and field in parent and child[field] != parent[field]:
            inherited = {key: parent[key] for key in retained if key in parent}
            break
    return {**inherited, **child}


def _source_scope(data: dict, row: dict, source_ref: dict) -> dict[str, Any] | None:
    node_ref = data.get("source_ref", {})
    if not isinstance(node_ref, dict):
        node_ref = {}
    node_aliases = {
        target: data[key]
        for key, target in (("source_doc_slug", "slug"), ("source_region_id", "region_id"))
        if key in data
    }
    node = _inherit_scope(node_aliases, node_ref)
    row_scope = dict(source_ref)
    if "source_region_id" in row:
        if "region_id" in row_scope and row_scope["region_id"] != row["source_region_id"]:
            return None
        row_scope["region_id"] = row["source_region_id"]
    scope = _inherit_scope(row_scope, node)
    detail = row_scope.get("detail")
    if row_scope.get("bbox") is not None or (
        isinstance(detail, dict) and detail.get("cell_bbox") is not None
    ):
        # The parent's marker says nothing about independently supplied boxes.
        scope["coord_origin"] = row_scope.get("coord_origin")
    if not isinstance(scope.get("slug"), str) or not scope["slug"].strip():
        return None
    page = scope.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        return None
    if "region_id" in scope and (
        not isinstance(scope["region_id"], str) or not scope["region_id"].strip()
    ):
        return None
    if scope.get("kind") not in (None, "pdf-page-bbox"):
        return None
    return scope
