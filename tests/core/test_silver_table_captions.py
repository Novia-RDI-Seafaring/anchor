"""Caption regressions for multi-column pages and embedded table titles."""
from __future__ import annotations

from copy import deepcopy

import pytest

from anchor.extensions.anchor_pdfs.core.silver import build_index


def _heading(text, bbox, *, page=1, path=None, order=0):
    return {
        "label": "section_header", "text": text, "page": page,
        "bbox": bbox, "group_path": path or [], "reading_order": order,
    }


def _table(cells=None, *, bbox=None, path=None, order=10):
    return {
        "label": "table", "page": 1, "bbox": bbox or [40, 200, 280, 280],
        "group_path": path or [], "reading_order": order, "cells": cells or [],
    }


def _title_cells():
    return [
        {"row": 0, "col": 0, "row_end": 1, "col_end": 2,
         "row_span": 1, "col_span": 2, "text": "Seal flush connections",
         "column_header": False, "row_header": False, "row_section": False,
         "bbox": [45, 201, 145, 210], "cell_id": "c0"},
        {"row": 1, "col": 0, "text": "Small models", "bbox": [45, 220, 140, 230]},
        {"row": 1, "col": 1, "text": "G thread", "bbox": [172, 220, 200, 230]},
        {"row": 2, "col": 0, "text": "Large models", "bbox": [45, 240, 140, 250]},
        {"row": 2, "col": 1, "text": "Tube", "bbox": [172, 240, 200, 250]},
    ]


def _caption(items, *, groups=None):
    return build_index({"items": items, "groups": groups or []})["tables"][0]["caption"]


def test_nearest_heading_above_full_width_table_beats_later_column_heading():
    # Norrhavn p1: Docling visits Design after the full-width table's title.
    items = [
        _heading("01 The range at a glance", [45, 608.77, 187, 620.73], order=8),
        _heading("Design", [394, 370.82, 425, 380.01], order=12),
        _table(bbox=[42, 630.12, 552, 718.91], order=15),
    ]
    assert _caption(items) == "01 The range at a glance"


def test_heading_selection_respects_page_group_and_column():
    items = [
        _heading("Left table", [45, 180, 100, 190], path=["left"], order=1),
        _heading("Other page", [45, 195, 100, 199], page=2, path=["left"], order=2),
        _heading("Sibling group", [45, 195, 100, 199], path=["right"], order=3),
        _heading("Other column", [310, 195, 400, 199], path=["left"], order=4),
        _table(path=["left"]),
    ]
    assert _caption(items) == "Left table"


@pytest.mark.parametrize("bbox", [[310, 180, 400, 190], [45, 220, 100, 230]])
def test_geometrically_unrelated_heading_does_not_leak_through_order_fallback(bbox):
    assert _caption([_heading("Unrelated", bbox), _table()]) == ""


def test_named_group_remains_fallback_when_heading_is_in_other_column():
    groups = [{"id": "limits", "label": "section", "name": "Limits"}]
    assert _caption([
        _heading("Other column", [310, 180, 400, 190], path=["limits"]),
        _table(path=["limits"]),
    ], groups=groups) == "Limits"


@pytest.mark.parametrize("missing", ["table", "heading"])
def test_missing_geometry_retains_preceding_header_fallback(missing):
    heading = _heading("Operating data", [45, 180, 100, 190])
    table = _table()
    (table if missing == "table" else heading).pop("bbox")
    assert _caption([heading, table]) == "Operating data"


def test_legacy_payload_without_tree_metadata_retains_reading_order_fallback():
    heading = _heading("Legacy heading", [310, 300, 400, 310])
    table = _table()
    table.pop("group_path")
    assert _caption([heading, table]) == "Legacy heading"


@pytest.mark.parametrize("text", ["Seal flush connections", "Operating limits"])
def test_table_wide_title_supplies_caption_without_changing_cells_or_geometry(text):
    table = _table(_title_cells())
    table["cells"][0]["text"] = text
    original = deepcopy(table)
    result = build_index({"items": [
        _heading("Double mechanical shaft seal", [45, 100, 180, 110]), table,
    ]})["tables"][0]
    assert result["caption"] == text
    assert result["cells"] == original["cells"]
    assert result["bbox"] == original["bbox"]
    assert table == original


def test_table_wide_title_can_use_span_metadata_without_end_offsets():
    cells = _title_cells()
    cells[0].pop("col_end")
    cells[0].pop("row_end")
    assert _caption([_table(cells)]) == "Seal flush connections"


def test_linked_caption_has_priority_over_embedded_title_and_spatial_heading():
    table = _table(_title_cells())
    table["captions"] = [{"text": "Table 4. Connections"}]
    assert _caption([
        _heading("A nearby heading", [45, 180, 180, 190]), table,
    ]) == "Table 4. Connections"


@pytest.mark.parametrize("text", ["120", "100 kPa", "1/8 G", "PX-5 - PX-70", "", "-"])
def test_numeric_table_wide_values_remain_data(text):
    cells = _title_cells()
    cells[0]["text"] = text
    assert _caption([_heading("Limits", [45, 180, 100, 190]), _table(cells)]) == "Limits"


@pytest.mark.parametrize("flag", ["column_header", "row_header"])
def test_spanning_header_rows_remain_data(flag):
    cells = _title_cells()
    cells[0][flag] = True
    assert _caption([_heading("Limits", [45, 180, 100, 190]), _table(cells)]) == "Limits"


def test_unspanned_first_row_is_not_promoted_when_its_value_is_missing():
    # Norrhavn p2 Temperature has this same ambiguous structure and no title flag.
    cells = _title_cells()
    cells[0].update(text="Temperature", col_span=1, col_end=1)
    assert _caption([
        _heading("Max inlet pressure", [45, 180, 150, 190]), _table(cells),
    ]) == "Max inlet pressure"


def test_ordinary_data_and_multi_cell_column_headers_are_not_titles():
    cells = _title_cells()[1:]
    for cell in cells:
        cell["row"] -= 1
    cells[0]["column_header"] = True
    cells[1]["column_header"] = True
    assert _caption([_heading("Limits", [45, 180, 100, 190]), _table(cells)]) == "Limits"


@pytest.mark.parametrize("change", ["short_body", "sparse_body", "row_span", "bad_span"])
def test_title_inference_requires_complete_unambiguous_body_rows(change):
    cells = _title_cells()
    if change == "short_body":
        cells = cells[:3]
    elif change == "sparse_body":
        cells.pop()
    elif change == "row_span":
        cells[0]["row_span"] = 2
    else:
        cells[0]["col_span"] = None
    assert _caption([_heading("Limits", [45, 180, 100, 190]), _table(cells)]) == "Limits"


def test_figure_caption_keeps_existing_reading_order_behavior():
    figure = {"label": "picture", "page": 1, "bbox": [45, 200, 100, 280], "group_path": []}
    result = build_index({"items": [
        _heading("Figure context", [310, 180, 400, 190]), figure,
    ]})
    assert result["figures"][0]["caption"] == "Figure context"
