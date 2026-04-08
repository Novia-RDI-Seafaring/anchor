"""Tests for silver.build_pages_meta."""
import json
from pathlib import Path
from typing import Any

from src.ingestion.silver import build_pages_meta

SILVER = Path(__file__).resolve().parents[1] / "data" / "silver"


def test_empty():
    out = build_pages_meta({"items": []})
    assert out == {"page_count": 0, "pages": {}}


def test_missing_items_key_safe():
    assert build_pages_meta({}) == {"page_count": 0, "pages": {}}


def test_label_histogram_and_item_ids():
    docling: dict[str, Any] = {"items": [
        {"label": "section_header", "page": 1, "bbox": [0, 100, 50, 90]},
        {"label": "text", "page": 1, "bbox": [0, 80, 50, 60]},
        {"label": "text", "page": 1, "bbox": [0, 50, 50, 30]},
        {"label": "section_header", "page": 2, "bbox": [0, 100, 50, 90]},
    ]}
    out = build_pages_meta(docling)
    assert out["page_count"] == 2
    assert out["pages"]["1"]["item_count"] == 3
    assert out["pages"]["1"]["labels"] == {"section_header": 1, "text": 2}
    assert out["pages"]["1"]["item_ids"] == ["p1-i0", "p1-i1", "p1-i2"]
    assert out["pages"]["2"]["item_count"] == 1


def test_bbox_union_bottomleft_orientation():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "page": 1, "bbox": [10, 200, 50, 180]},
        {"label": "text", "page": 1, "bbox": [5, 150, 80, 100]},
    ]}
    out = build_pages_meta(docling)
    union = out["pages"]["1"]["bbox_union"]
    # left=min, top=max (BOTTOMLEFT), right=max, bottom=min
    assert union == [5, 200, 80, 100]


def test_alfa_laval_real_doc():
    docling = json.loads((SILVER / "alfa-laval-lkh-centrifugal-pump" / "docling.json").read_text())
    meta = build_pages_meta(docling)
    assert meta["page_count"] == 4
    for p in ["1", "2", "3", "4"]:
        assert p in meta["pages"]
        assert meta["pages"][p]["item_count"] > 0
        assert len(meta["pages"][p]["bbox_union"]) == 4
