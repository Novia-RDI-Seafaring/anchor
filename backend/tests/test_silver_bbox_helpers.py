"""Tests for silver bbox helpers — fuzzy text match, union, snap."""
from typing import Any

from src.ingestion.silver import (
    bbox_center,
    find_items_by_text,
    point_in_bbox,
    snap_to_docling_items,
    union_bbox,
)


# ── find_items_by_text ───────────────────────────────────────────────────────


def test_find_items_by_text_case_insensitive():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [0, 100, 50, 80], "text": "Max Inlet Pressure"},
        {"label": "text", "page": 1, "bbox": [0, 80, 50, 60], "text": "irrelevant"},
    ]}
    out = find_items_by_text(docling, "max inlet")
    assert len(out) == 1
    assert out[0]["text"] == "Max Inlet Pressure"


def test_find_items_by_text_page_scoped():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [0, 0, 1, 1], "text": "LKH-5"},
        {"label": "text", "page": 2, "bbox": [0, 0, 1, 1], "text": "LKH-5"},
    ]}
    out = find_items_by_text(docling, "LKH-5", page=2)
    assert len(out) == 1
    assert out[0]["page"] == 2


def test_find_items_by_text_empty_needle():
    assert find_items_by_text({"items": [{"label": "text", "page": 1, "bbox": [0, 0, 1, 1], "text": "x"}]}, "") == []


def test_find_items_by_text_normalized_whitespace():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [0, 0, 1, 1], "text": "Foo   bar\tbaz"},
    ]}
    assert len(find_items_by_text(docling, "foo bar baz")) == 1


# ── union_bbox ───────────────────────────────────────────────────────────────


def test_union_bbox_single():
    assert union_bbox([[10, 100, 20, 80]]) == [10, 100, 20, 80]


def test_union_bbox_multi_bottomleft():
    out = union_bbox([[10, 100, 20, 80], [5, 90, 25, 60]])
    assert out == [5, 100, 25, 60]


def test_union_bbox_empty():
    assert union_bbox([]) == []


def test_union_bbox_skips_invalid():
    assert union_bbox([[1, 2, 3], [10, 100, 20, 80]]) == [10, 100, 20, 80]


# ── point_in_bbox ────────────────────────────────────────────────────────────


def test_point_in_bbox_inside():
    assert point_in_bbox((15, 90), [10, 100, 20, 80]) is True


def test_point_in_bbox_outside():
    assert point_in_bbox((5, 90), [10, 100, 20, 80]) is False
    assert point_in_bbox((15, 110), [10, 100, 20, 80]) is False


def test_point_in_bbox_on_edge():
    assert point_in_bbox((10, 100), [10, 100, 20, 80]) is True


def test_bbox_center():
    assert bbox_center([0, 100, 20, 80]) == (10, 90)
    assert bbox_center([1, 2, 3]) is None


# ── snap_to_docling_items ────────────────────────────────────────────────────


def test_snap_collects_items_inside_approx_bbox():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [10, 100, 30, 80], "text": "a"},   # center 20,90 ✓
        {"label": "text", "page": 1, "bbox": [40, 100, 60, 80], "text": "b"},   # center 50,90 ✗
        {"label": "text", "page": 1, "bbox": [12, 75, 28, 60], "text": "c"},    # center 20,67.5 ✓
        {"label": "text", "page": 2, "bbox": [10, 100, 30, 80], "text": "wrong page"},
    ]}
    snapped, indices = snap_to_docling_items(docling, page=1, approx_bbox=[5, 110, 35, 50])
    assert indices == [0, 2]
    # union of items 0 and 2: left=min(10,12)=10, top=max(100,75)=100, right=max(30,28)=30, bottom=min(80,60)=60
    assert snapped == [10, 100, 30, 60]


def test_snap_returns_empty_when_nothing_inside():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [100, 100, 150, 80]},
    ]}
    snapped, indices = snap_to_docling_items(docling, page=1, approx_bbox=[0, 50, 10, 0])
    assert snapped == []
    assert indices == []


def test_snap_handles_invalid_bbox():
    snapped, indices = snap_to_docling_items({"items": []}, page=1, approx_bbox=[1, 2, 3])
    assert snapped == []
    assert indices == []
