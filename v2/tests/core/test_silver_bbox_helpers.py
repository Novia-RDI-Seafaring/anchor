"""Tests for bbox helpers (snap, union, find by text)."""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.silver import (
    bbox_center,
    find_items_by_text,
    point_in_bbox,
    snap_to_docling_items,
    union_bbox,
)


def test_bbox_center_returns_midpoint():
    assert bbox_center([0, 100, 50, 0]) == (25, 50)


def test_bbox_center_returns_none_on_bad_shape():
    assert bbox_center([1, 2]) is None


def test_point_in_bbox_bottomleft_semantics():
    bbox = [0, 100, 50, 0]  # left, top, right, bottom (BOTTOMLEFT)
    assert point_in_bbox((25, 50), bbox)
    assert not point_in_bbox((-1, 50), bbox)
    assert not point_in_bbox((25, 200), bbox)


def test_union_bbox_combines_extents():
    u = union_bbox([[10, 100, 20, 50], [15, 110, 30, 40]])
    assert u == [10, 110, 30, 40]


def test_union_empty_returns_empty():
    assert union_bbox([]) == []


def test_find_items_by_text_case_insensitive():
    docling = {"items": [
        {"label": "text", "text": "Max inlet pressure", "page": 1, "bbox": [0, 0, 0, 0]},
        {"label": "text", "text": "Other", "page": 1, "bbox": [0, 0, 0, 0]},
    ]}
    out = find_items_by_text(docling, "INLET")
    assert len(out) == 1
    assert out[0]["text"] == "Max inlet pressure"


def test_find_items_filters_by_page():
    docling = {"items": [
        {"label": "text", "text": "match", "page": 1, "bbox": [0, 0, 0, 0]},
        {"label": "text", "text": "match", "page": 2, "bbox": [0, 0, 0, 0]},
    ]}
    assert len(find_items_by_text(docling, "match", page=1)) == 1


def test_snap_absorbs_items_with_centers_inside_approx():
    docling = {"items": [
        {"label": "text", "text": "a", "page": 1, "bbox": [10, 100, 20, 80]},   # center (15, 90) — inside
        {"label": "text", "text": "b", "page": 1, "bbox": [15, 95, 25, 85]},    # center (20, 90) — inside
        {"label": "text", "text": "c", "page": 1, "bbox": [200, 50, 250, 30]},  # outside
    ]}
    snapped, idxs = snap_to_docling_items(docling, page=1, approx_bbox=[5, 110, 30, 70])
    assert idxs == [0, 1]
    assert snapped == [10, 100, 25, 80]


def test_snap_returns_empty_for_invalid_bbox():
    docling = {"items": [{"label": "text", "page": 1, "bbox": [0, 0, 0, 0]}]}
    assert snap_to_docling_items(docling, 1, [1, 2, 3]) == ([], [])
