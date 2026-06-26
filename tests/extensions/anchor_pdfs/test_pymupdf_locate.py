"""locate_text renderer: page-space quad in the region-bbox coordinate space.

Slice 2 of #145 (issue #197). Given a value and (optionally) a region bbox,
PyMuPDF `page.search_for` finds the text; we convert the TOPLEFT match rect
back to the BOTTOMLEFT origin gold/region bboxes use so the returned quad rides
through the frontend's `bboxToImageRect` mapping unchanged. Not-found returns an
empty list so the caller falls back to the region-level highlight.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import _locate_text_sync

PAGE_W = 595.3
PAGE_H = 841.9


@pytest.fixture()
def text_pdf(tmp_path: Path) -> Path:
    """A one-page PDF with two known strings at known TOPLEFT positions.

    `LKH-5` near the top, the repeated token `600 kPa` once near the top and
    once near the bottom (to exercise within_bbox disambiguation).
    """
    path = tmp_path / "text.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text((100, 100), "LKH-5", fontsize=12)
    page.insert_text((100, 120), "600 kPa", fontsize=12)
    page.insert_text((100, 700), "600 kPa", fontsize=12)
    doc.save(path)
    doc.close()
    return path


def _bl_to_tl_top(quad: list[float]) -> float:
    """Image-space top edge for a returned BOTTOMLEFT quad (yHigh -> top)."""
    _, yb0, _, yb1 = quad
    return PAGE_H - max(yb0, yb1)


def test_locates_known_value(text_pdf: Path) -> None:
    quads = _locate_text_sync(text_pdf, 1, "LKH-5", None)
    assert quads, "expected a non-empty quad for a known value"
    left, _, right, _ = quads[0]
    assert right > left
    # Inserted at baseline TOPLEFT y=100; the glyph box top sits just above the
    # baseline, so the image top edge lands a little under 100.
    assert _bl_to_tl_top(quads[0]) == pytest.approx(92, abs=15)


def test_returns_bottomleft_ascending_quads(text_pdf: Path) -> None:
    quads = _locate_text_sync(text_pdf, 1, "LKH-5", None)
    left, yb0, right, yb1 = quads[0]
    assert left <= right
    assert yb0 <= yb1
    # BOTTOMLEFT: a top-of-page match has a large y (page height minus a small
    # TOPLEFT y), so it sits high in PDF user-space.
    assert yb1 > PAGE_H / 2


def test_within_bbox_disambiguates_repeats(text_pdf: Path) -> None:
    # Both copies match with no clip.
    assert len(_locate_text_sync(text_pdf, 1, "600 kPa", None)) == 2
    # Clip to the TOP region (BOTTOMLEFT bbox covering the upper band only) ->
    # only the top copy. BOTTOMLEFT y for the top band is the high end.
    top_region = [80.0, PAGE_H - 80.0, 300.0, PAGE_H - 200.0]
    top_hits = _locate_text_sync(text_pdf, 1, "600 kPa", top_region)
    assert len(top_hits) == 1
    assert _bl_to_tl_top(top_hits[0]) == pytest.approx(112, abs=15)


def test_not_found_returns_empty(text_pdf: Path) -> None:
    assert _locate_text_sync(text_pdf, 1, "no-such-token-xyz", None) == []


def test_blank_query_returns_empty(text_pdf: Path) -> None:
    assert _locate_text_sync(text_pdf, 1, "   ", None) == []


def test_out_of_range_page_returns_empty(text_pdf: Path) -> None:
    assert _locate_text_sync(text_pdf, 99, "LKH-5", None) == []
