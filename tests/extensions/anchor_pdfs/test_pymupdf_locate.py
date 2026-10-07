"""locate_text renderer: page-space quad in the region-bbox coordinate space.

Slice 2 of #145 (issue #197). Given a value and (optionally) a region bbox,
PyMuPDF `page.search_for` finds the text. Region bboxes and PyMuPDF share the
canonical top-left PDF-points convention (#281), so the match rect is returned
as-is (order-normalised) and rides through the frontend's `bboxToImageRect`
mapping unchanged. Not-found returns an empty list so the caller falls back to
the region-level highlight.
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


def _top(quad: list[float]) -> float:
    """Top edge of a returned top-left quad."""
    _, y0, _, y1 = quad
    return min(y0, y1)


def test_locates_known_value(text_pdf: Path) -> None:
    quads = _locate_text_sync(text_pdf, 1, "LKH-5", None)
    assert quads, "expected a non-empty quad for a known value"
    left, _, right, _ = quads[0]
    assert right > left
    # Inserted at baseline TOPLEFT y=100; the glyph box top sits just above the
    # baseline, so the image top edge lands a little under 100.
    assert _top(quads[0]) == pytest.approx(92, abs=15)


def test_returns_topleft_ascending_quads(text_pdf: Path) -> None:
    quads = _locate_text_sync(text_pdf, 1, "LKH-5", None)
    left, y0, right, y1 = quads[0]
    assert left <= right
    assert y0 <= y1
    # Top-left: a top-of-page match has a small y.
    assert y1 < PAGE_H / 2


def test_within_bbox_disambiguates_repeats(text_pdf: Path) -> None:
    # Both copies match with no clip.
    assert len(_locate_text_sync(text_pdf, 1, "600 kPa", None)) == 2
    # Clip to the TOP region (top-left bbox covering the upper band only) ->
    # only the top copy.
    top_region = [80.0, 80.0, 300.0, 200.0]
    top_hits = _locate_text_sync(text_pdf, 1, "600 kPa", top_region)
    assert len(top_hits) == 1
    assert _top(top_hits[0]) == pytest.approx(112, abs=15)


def test_not_found_returns_empty(text_pdf: Path) -> None:
    assert _locate_text_sync(text_pdf, 1, "no-such-token-xyz", None) == []


def test_blank_query_returns_empty(text_pdf: Path) -> None:
    assert _locate_text_sync(text_pdf, 1, "   ", None) == []


def test_out_of_range_page_returns_empty(text_pdf: Path) -> None:
    assert _locate_text_sync(text_pdf, 99, "LKH-5", None) == []
