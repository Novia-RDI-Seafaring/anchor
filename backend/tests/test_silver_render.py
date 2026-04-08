"""Tests for silver page renderers (markdown + png)."""
import json
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.silver import render_pages_md, render_pages_png

TESTS_DIR = Path(__file__).resolve().parent
SILVER = TESTS_DIR.parents[0] / "data" / "silver" / "alfa-laval-lkh-centrifugal-pump"
PDF = TESTS_DIR / "alfa-laval-lkh-centrifugal-pump.pdf"


# ── render_pages_md ──────────────────────────────────────────────────────────


def test_render_pages_md_empty():
    assert render_pages_md({"items": []}) == {}


def test_render_pages_md_missing_items_key():
    assert render_pages_md({}) == {}


def test_render_pages_md_orders_top_to_bottom():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "text": "second", "page": 1, "bbox": [0, 200, 100, 180]},
        {"label": "text", "text": "first", "page": 1, "bbox": [0, 500, 100, 480]},
    ]}
    md = render_pages_md(docling)[1]
    assert md.index("first") < md.index("second")


def test_render_pages_md_section_header_levels():
    docling: dict[str, Any] = {"items": [
        {"label": "section_header", "text": "TECHNICAL DATA", "page": 1, "bbox": [0, 700, 100, 690]},
        {"label": "section_header", "text": "Materials", "page": 1, "bbox": [0, 600, 100, 590]},
    ]}
    md = render_pages_md(docling)[1]
    assert "## TECHNICAL DATA" in md
    assert "### Materials" in md


def test_render_pages_md_lists_and_text():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "text": "Intro paragraph.", "page": 1, "bbox": [0, 700, 100, 690]},
        {"label": "list_item", "text": "first bullet", "page": 1, "bbox": [0, 680, 100, 670]},
        {"label": "list_item", "text": "second bullet", "page": 1, "bbox": [0, 660, 100, 650]},
    ]}
    md = render_pages_md(docling)[1]
    assert "Intro paragraph." in md
    assert "- first bullet" in md
    assert "- second bullet" in md


def test_render_pages_md_table_as_gfm():
    cells = [
        {"row": 0, "col": 0, "text": "Model"},
        {"row": 0, "col": 1, "text": "kPa"},
        {"row": 1, "col": 0, "text": "LKH-5"},
        {"row": 1, "col": 1, "text": "400"},
    ]
    docling: dict[str, Any] = {"items": [
        {"label": "table", "page": 1, "bbox": [0, 500, 200, 400], "cells": cells},
    ]}
    md = render_pages_md(docling)[1]
    assert "| Model | kPa |" in md
    assert "| --- | --- |" in md
    assert "| LKH-5 | 400 |" in md


def test_render_pages_md_pipe_in_cell_escaped():
    cells = [
        {"row": 0, "col": 0, "text": "a|b"},
        {"row": 0, "col": 1, "text": "c"},
    ]
    docling: dict[str, Any] = {"items": [
        {"label": "table", "page": 1, "bbox": [0, 0, 1, 1], "cells": cells},
    ]}
    md = render_pages_md(docling)[1]
    assert "a\\|b" in md


def test_render_pages_md_picture_placeholder():
    docling: dict[str, Any] = {"items": [
        {"label": "picture", "text": "", "page": 1, "bbox": [0, 0, 1, 1]},
    ]}
    md = render_pages_md(docling)[1]
    assert "_[figure: figure]_" in md


def test_render_pages_md_groups_by_page():
    docling: dict[str, Any] = {"items": [
        {"label": "text", "text": "p1", "page": 1, "bbox": [0, 0, 1, 1]},
        {"label": "text", "text": "p2", "page": 2, "bbox": [0, 0, 1, 1]},
    ]}
    out = render_pages_md(docling)
    assert set(out.keys()) == {1, 2}
    assert "p1" in out[1] and "p2" not in out[1]
    assert "p2" in out[2] and "p1" not in out[2]


# ── alfa-laval real-doc smoke ────────────────────────────────────────────────


def test_render_pages_md_alfa_laval_has_4_pages_with_known_content():
    docling = json.loads((SILVER / "docling.json").read_text())
    out = render_pages_md(docling)
    assert set(out.keys()) == {1, 2, 3, 4}
    # Page 1: introduction text
    assert "Alfa Laval LKH" in out[1]
    assert "Cleaning-in-Place" in out[1]
    # Page 2: tech data + materials
    assert "TECHNICAL DATA" in out[2]
    assert "Materials" in out[2]
    assert "LKH-5" in out[2]  # max inlet pressure rows
    # Page 3: dimensions tables with all models
    assert "Pump Model" in out[3]
    assert "LKH-90" in out[3]
    assert "IEC80" in out[3]
    # Page 4: flow chart + ordering
    assert "Flow chart" in out[4]
    assert "Ordering" in out[4]


# ── render_pages_png ─────────────────────────────────────────────────────────


@pytest.mark.skipif(not PDF.exists(), reason="alfa-laval pdf not present in tests/")
def test_render_pages_png_alfa_laval(tmp_path: Path):
    written = render_pages_png(PDF, tmp_path, dpi=72)  # low dpi keeps the test cheap
    assert len(written) == 4
    for i, p in enumerate(written, start=1):
        assert p == tmp_path / f"{i}.png"
        assert p.exists()
        assert p.stat().st_size > 0
