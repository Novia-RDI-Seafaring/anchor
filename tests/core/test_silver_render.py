"""Tests for render_pages_md and table rendering — pure functions."""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.silver import render_pages_md


def test_empty_docling_returns_empty_dict():
    assert render_pages_md({}) == {}


def test_renders_title_as_h1():
    docling = {"items": [
        {"label": "title", "text": "Hello", "page": 1, "bbox": [0, 700, 100, 720]},
    ]}
    out = render_pages_md(docling)
    assert "# Hello" in out[1]


def test_section_headers_become_h2_or_h3():
    docling = {"items": [
        {"label": "section_header", "text": "INTRODUCTION", "page": 1, "bbox": [0, 700, 100, 720]},
        {"label": "section_header", "text": "subsection details", "page": 1, "bbox": [0, 600, 200, 620]},
    ]}
    out = render_pages_md(docling)
    # ALL-CAPS short → level 1 → h2 (one above level)
    assert "## INTRODUCTION" in out[1]
    # mixed-case → level 2 → h3
    assert "### subsection details" in out[1]


def test_text_paragraphs_emitted_unchanged():
    docling = {"items": [
        {"label": "text", "text": "A paragraph.", "page": 1, "bbox": [0, 600, 200, 620]},
    ]}
    assert "A paragraph." in render_pages_md(docling)[1]


def test_list_items_become_dashes():
    docling = {"items": [
        {"label": "list_item", "text": "first", "page": 1, "bbox": [0, 700, 100, 720]},
        {"label": "list_item", "text": "second", "page": 1, "bbox": [0, 690, 100, 705]},
    ]}
    md = render_pages_md(docling)[1]
    assert "- first" in md
    assert "- second" in md


def test_picture_renders_as_figure_marker():
    docling = {"items": [
        {"label": "picture", "text": "diagram", "page": 1, "bbox": [0, 600, 100, 700]},
    ]}
    md = render_pages_md(docling)[1]
    assert "_[figure: diagram]_" in md


def test_table_renders_as_gfm():
    docling = {"items": [
        {"label": "table", "page": 1, "bbox": [0, 600, 100, 700], "cells": [
            {"row": 0, "col": 0, "text": "A"},
            {"row": 0, "col": 1, "text": "B"},
            {"row": 1, "col": 0, "text": "1"},
            {"row": 1, "col": 1, "text": "2"},
        ]},
    ]}
    md = render_pages_md(docling)[1]
    assert "| A | B |" in md
    assert "| --- | --- |" in md
    assert "| 1 | 2 |" in md


def test_table_distinct_cells_at_same_coordinate_are_coalesced_not_dropped():
    # Two distinct cell texts at the same (row, col) must both survive
    # (issue #129: missing / collapsed values). A plain dict assignment
    # would keep only the last and silently drop "A".
    docling = {"items": [
        {"label": "table", "page": 1, "bbox": [0, 600, 100, 700], "cells": [
            {"row": 0, "col": 0, "text": "A"},
            {"row": 0, "col": 0, "text": "B"},
        ]},
    ]}
    md = render_pages_md(docling)[1]
    assert "A" in md and "B" in md


def test_table_identical_span_text_at_same_coordinate_is_deduped():
    # Docling repeats a spanned cell's text across the positions it covers;
    # identical text must collapse to one (no "PUMP PUMP").
    docling = {"items": [
        {"label": "table", "page": 1, "bbox": [0, 600, 100, 700], "cells": [
            {"row": 0, "col": 0, "text": "PUMP"},
            {"row": 0, "col": 0, "text": "PUMP"},
        ]},
    ]}
    md = render_pages_md(docling)[1]
    assert "PUMP PUMP" not in md
    assert "| PUMP |" in md


def test_pages_grouped_by_page_number():
    docling = {"items": [
        {"label": "text", "text": "p1", "page": 1, "bbox": [0, 600, 100, 620]},
        {"label": "text", "text": "p2", "page": 2, "bbox": [0, 600, 100, 620]},
    ]}
    out = render_pages_md(docling)
    assert "p1" in out[1] and "p1" not in out[2]
    assert "p2" in out[2] and "p2" not in out[1]


def test_reading_order_top_to_bottom():
    docling = {"items": [
        # bottom item (low top y)
        {"label": "text", "text": "bottom", "page": 1, "bbox": [0, 100, 100, 120]},
        # top item (high top y)
        {"label": "text", "text": "top", "page": 1, "bbox": [0, 700, 100, 720]},
    ]}
    md = render_pages_md(docling)[1]
    assert md.index("top") < md.index("bottom")
