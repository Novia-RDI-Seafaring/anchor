"""The bbox contract at the extractor boundary (#281).

Every PdfExtractor must deliver top-left PDF points; `normalize_items` is the
one place that guarantees it, so a second extractor cannot ship flipped or
out-of-page boxes silently.
"""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.core.silver import (
    BBOX_ORIGIN,
    build_pages_meta,
    flip_bbox_y,
    normalize_items,
)

_PAGES = {1: {"width": 600.0, "height": 800.0}}


def test_flip_bbox_y_is_its_own_inverse_and_normalises_order():
    assert flip_bbox_y([10, 700, 50, 680], 800) == [10, 100, 50, 120]
    assert flip_bbox_y([10, 100, 50, 120], 800) == [10, 680, 50, 700]
    assert flip_bbox_y([1, 2, 3], 800) == []


def test_top_left_input_passes_through_with_order_normalised():
    docling = {
        "items": [{"label": "text", "text": "a", "page": 1, "bbox": [10, 120, 50, 100]}],
        "pages": _PAGES,
    }
    out = normalize_items(docling)
    assert out["coord_origin"] == BBOX_ORIGIN
    assert out["items"][0]["bbox"] == [10.0, 100.0, 50.0, 120.0]


def test_bottom_left_extractor_is_converted_with_page_height():
    docling = {
        "items": [
            {"label": "text", "text": "a", "page": 1, "bbox": [10, 700, 50, 680]},
            {"label": "table", "text": "", "page": 1, "bbox": [0, 400, 600, 100],
             "cells": [{"row": 0, "col": 0, "text": "x", "bbox": [0, 390, 100, 370]}]},
        ],
        "tables": [{"page": 1, "bbox": [0, 400, 600, 100], "cells": []}],
        "pages": _PAGES,
        "coord_origin": "bottom-left",
    }
    out = normalize_items(docling)
    assert out["coord_origin"] == BBOX_ORIGIN
    assert out["items"][0]["bbox"] == [10.0, 100.0, 50.0, 120.0]
    assert out["items"][1]["bbox"] == [0.0, 400.0, 600.0, 700.0]
    assert out["items"][1]["cells"][0]["bbox"] == [0.0, 410.0, 100.0, 430.0]
    assert out["tables"][0]["bbox"] == [0.0, 400.0, 600.0, 700.0]


def test_bottom_left_without_page_sizes_fails_loudly():
    docling = {
        "items": [{"label": "text", "text": "a", "page": 1, "bbox": [10, 700, 50, 680]}],
        "coord_origin": "bottom-left",
    }
    with pytest.raises(ValueError):
        normalize_items(docling)


def test_unknown_origin_is_rejected():
    with pytest.raises(ValueError):
        normalize_items({"items": [], "coord_origin": "center"})


def test_out_of_page_boxes_are_clamped_and_bad_boxes_dropped():
    docling = {
        "items": [
            {"label": "text", "text": "a", "page": 1, "bbox": [-5, -10, 700, 900]},
            {"label": "text", "text": "b", "page": 1, "bbox": [1, 2, 3]},
            {"label": "text", "text": "c", "page": 1, "bbox": "nope"},
        ],
        "pages": _PAGES,
    }
    out = normalize_items(docling)
    assert out["items"][0]["bbox"] == [0.0, 0.0, 600.0, 800.0]
    assert out["items"][1]["bbox"] == []
    assert out["items"][2]["bbox"] == []


def test_pages_meta_carries_page_size_and_origin_stamp():
    docling = {
        "items": [
            {"label": "title", "text": "T", "page": 1, "bbox": [0, 10, 100, 30]},
            {"label": "text", "text": "p", "page": 1, "bbox": [0, 40, 200, 60]},
        ],
        "pages": _PAGES,
    }
    meta = build_pages_meta(docling)
    assert meta["bbox_origin"] == "top-left"
    assert meta["pages"]["1"]["page_size"] == [600.0, 800.0]
    assert meta["pages"]["1"]["bbox_union"] == [0, 10, 200, 60]
