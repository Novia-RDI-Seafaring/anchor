"""Docling's text boxes are as tall as the font's line; the PDF's words are
the glyphs. Extraction shrinks the one to the other, so a highlight on one
row of a dense table does not reach into the next."""

from __future__ import annotations

import fitz

from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import tighten_to_glyphs


def _pdf(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((116, 262), "80", fontsize=9)
    page.insert_text((116, 276.5), "75", fontsize=9)
    path = tmp_path / "rows.pdf"
    doc.save(str(path))
    return path


def test_text_and_cell_boxes_shrink_to_the_glyphs(tmp_path):
    path = _pdf(tmp_path)
    flat = {
        "items": [
            {"label": "text", "text": "80", "page": 1, "bbox": [110, 245, 135, 269]},
            {"label": "table", "text": "", "page": 1, "bbox": [100, 240, 300, 300],
             "cells": [{"row": 1, "col": 1, "text": "75", "bbox": [110, 259.5, 135, 283.5]}]},
            {"label": "picture", "text": "", "page": 1, "bbox": [0, 0, 50, 50]},
        ]
    }
    out = tighten_to_glyphs(flat, path)
    text, table, picture = out["items"]
    # No taller than the glyphs plus a little room, and never grown.
    assert text["bbox"][3] - text["bbox"][1] < 14
    assert text["bbox"][1] >= 245 and text["bbox"][3] <= 269
    cell = table["cells"][0]["bbox"]
    assert cell[3] - cell[1] < 14
    # The row above's glyphs end above the next row's cell.
    assert text["bbox"][3] <= cell[1] + 2
    assert table["bbox"] == [100, 240, 300, 300]
    assert picture["bbox"] == [0, 0, 50, 50]


def test_a_box_with_no_words_is_left_alone(tmp_path):
    path = _pdf(tmp_path)
    flat = {"items": [{"label": "text", "text": "scan", "page": 1, "bbox": [400, 600, 500, 640]}]}
    assert tighten_to_glyphs(flat, path)["items"][0]["bbox"] == [400, 600, 500, 640]


def test_a_box_that_also_holds_the_row_above_keeps_its_own_words(tmp_path):
    path = _pdf(tmp_path)
    # Tall enough to hold the "80" above as well as its own "75".
    flat = {"items": [{"label": "text", "text": "75", "page": 1, "bbox": [110, 250, 135, 282]}]}
    box = tighten_to_glyphs(flat, path)["items"][0]["bbox"]
    assert box[1] > 266  # below the "80"
    assert box[3] - box[1] < 14
