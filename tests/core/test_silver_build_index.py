"""Tests for build_index - pure dict to dict, no I/O."""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.silver import (
    build_index,
    point_in_bbox,
    table_bbox_from_items,
    table_cells_from_items,
)


def test_empty_docling_yields_empty_index():
    idx = build_index({})
    assert idx["document"]["page_count"] == 0
    assert idx["outline"] == []
    assert idx["tables"] == []
    assert idx["figures"] == []


def test_outline_picks_up_titles_and_section_headers():
    docling = {"items": [
        {"label": "title", "text": "Pump Datasheet", "page": 1, "bbox": [10, 700, 300, 730]},
        {"label": "section_header", "text": "Operating Limits", "page": 2, "bbox": [10, 600, 200, 620]},
    ]}
    idx = build_index(docling, filename="pump.pdf")
    assert idx["document"]["filename"] == "pump.pdf"
    assert idx["document"]["title"] == "Pump Datasheet"
    assert len(idx["outline"]) == 2
    assert idx["outline"][0]["title"] == "Pump Datasheet"
    assert idx["outline"][0]["level"] == 1


def test_tables_carry_caption_from_preceding_header():
    docling = {"items": [
        {"label": "section_header", "text": "Materials", "page": 2, "bbox": [10, 700, 100, 720]},
        {"label": "table", "page": 2, "bbox": [10, 500, 400, 690],
         "cells": [
             {"row": 0, "col": 0, "text": "Part"},
             {"row": 0, "col": 1, "text": "Material"},
             {"row": 1, "col": 0, "text": "Casing"},
             {"row": 1, "col": 1, "text": "Steel", "bbox": [200, 500, 260, 480]},
         ]},
    ]}
    idx = build_index(docling)
    assert len(idx["tables"]) == 1
    table = idx["tables"][0]
    assert table["caption"] == "Materials"
    assert table["header_row"] == ["Part", "Material"]
    assert table["first_column_values"] == ["Casing"]
    assert table["shape"] == {"rows": 2, "cols": 2}
    assert table["cells"][-1] == {
        "row": 1,
        "col": 1,
        "text": "Steel",
        "bbox": [200.0, 500.0, 260.0, 480.0],
    }


def test_figures_recorded():
    docling = {"items": [
        {"label": "picture", "page": 3, "bbox": [50, 600, 350, 750]},
    ]}
    idx = build_index(docling)
    assert len(idx["figures"]) == 1
    assert idx["figures"][0]["page"] == 3


def test_page_count_is_max_observed():
    docling = {"items": [
        {"label": "text", "text": "p1", "page": 1, "bbox": [0, 0, 0, 0]},
        {"label": "text", "text": "p4", "page": 4, "bbox": [0, 0, 0, 0]},
    ]}
    assert build_index(docling)["document"]["page_count"] == 4


def test_title_falls_back_to_first_section_header():
    docling = {"items": [
        {"label": "section_header", "text": "Introduction", "page": 1, "bbox": [0, 0, 0, 0]},
    ]}
    idx = build_index(docling)
    assert idx["document"]["title"] == "Introduction"


def test_explicit_title_wins_over_first_header():
    docling = {"items": [
        {"label": "section_header", "text": "Introduction", "page": 1, "bbox": [0, 0, 0, 0]},
    ]}
    idx = build_index(docling, title="Override")
    assert idx["document"]["title"] == "Override"


def test_table_cells_from_items_returns_selected_table_cells():
    items = [
        {"label": "text", "text": "Intro", "bbox": [0, 100, 80, 90]},
        {
            "label": "table",
            "bbox": [10, 100, 110, 10],
            "cells": [
                {"row": 0, "col": 0, "text": "Field", "bbox": [20, 90, 40, 80]},
                {"row": 0, "col": 1, "text": "Value", "bbox": [50, 90, 80, 80]},
            ],
        },
    ]

    assert table_cells_from_items(items, [1]) == [
        {"row": 0, "col": 0, "text": "Field", "bbox": [20.0, 90.0, 40.0, 80.0]},
        {"row": 0, "col": 1, "text": "Value", "bbox": [50.0, 90.0, 80.0, 80.0]},
    ]
    assert table_cells_from_items(items, [0]) == []


def test_table_cells_from_items_prefers_best_geometric_fit():
    items = [
        {
            "label": "table",
            "bbox": [0, 100, 100, 80],
            "cells": [{"row": 0, "col": 0, "text": "Small", "bbox": [10, 95, 30, 90]}],
        },
        {
            "label": "table",
            "bbox": [0, 70, 200, 10],
            "cells": [{"row": 0, "col": 0, "text": "Large", "bbox": [10, 65, 30, 60]}],
        },
    ]

    region_bbox = [0, 110, 220, 0]

    assert table_cells_from_items(items, [0, 1], region_bbox=region_bbox) == [
        {"row": 0, "col": 0, "text": "Large", "bbox": [10.0, 65.0, 30.0, 60.0]},
    ]
    assert table_bbox_from_items(items, [0, 1], region_bbox=region_bbox) == [
        0.0,
        70.0,
        200.0,
        10.0,
    ]


def test_point_in_bbox_tolerates_reversed_y_order():
    assert point_in_bbox((5, 5), [0, 0, 10, 10]) is True
    assert point_in_bbox((5, 5), [0, 10, 10, 0]) is True
    assert point_in_bbox((5, 5), [10, 10, 0, 0]) is False
