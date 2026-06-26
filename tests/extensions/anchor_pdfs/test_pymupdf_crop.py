"""Region crop renderer: bbox-order-independent, never an inverted rect.

Regression for #171: gold bboxes are stored ascending-y ([x0, y0, x1, y1] with
y0 < y1). The old code did a fixed bottom-left->top-left flip and built the rect
directly, so ascending-y input produced an inverted (y0 > y1) rect and PyMuPDF
raised FzErrorArgument -> the crop endpoint 500'd and the canvas node fell back
to the full page image.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pymupdf
import pytest

from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import _crop_region_sync

# Mirrors the verified repro: doc alfa-laval-lkh-centrifugal-pump page 1, region
# r7. Page height 841.9, bbox ascending-y -> old code built Rect(309.7, 464.6,
# 594.3, 212.7) with y0 > y1.
PAGE_W = 595.3
PAGE_H = 841.9
REPRO_BBOX = [309.7, 377.3, 594.3, 629.2]


def _png_dims(data: bytes) -> tuple[int, int]:
    """Decode PNG width/height from the IHDR header (stdlib only; no PIL)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


@pytest.fixture()
def blank_pdf(tmp_path: Path) -> Path:
    """A one-page PDF the size of the real doc page (blank content is fine)."""
    path = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page(width=PAGE_W, height=PAGE_H)
    doc.save(path)
    doc.close()
    return path


def _full_page_dims(pdf_path: Path, dpi: int) -> tuple[int, int]:
    with pymupdf.open(pdf_path) as doc:
        png = doc[0].get_pixmap(dpi=dpi).tobytes("png")
    return _png_dims(png)


def test_ascending_y_bbox_yields_subpage_png(blank_pdf: Path) -> None:
    """An ascending-y bbox renders a non-empty crop smaller than the full page."""
    dpi = 300
    png = _crop_region_sync(blank_pdf, 1, REPRO_BBOX, "png", dpi)

    assert png, "crop PNG is empty"
    crop_w, crop_h = _png_dims(png)
    full_w, full_h = _full_page_dims(blank_pdf, dpi)

    assert crop_w > 0 and crop_h > 0
    assert crop_w < full_w, f"crop width {crop_w} not < page {full_w}"
    assert crop_h < full_h, f"crop height {crop_h} not < page {full_h}"


def test_bbox_order_independent(blank_pdf: Path) -> None:
    """Ascending- and descending-y orderings of the same region crop alike."""
    dpi = 300
    ascending = REPRO_BBOX
    descending = [REPRO_BBOX[0], REPRO_BBOX[3], REPRO_BBOX[2], REPRO_BBOX[1]]

    asc_dims = _png_dims(_crop_region_sync(blank_pdf, 1, ascending, "png", dpi))
    desc_dims = _png_dims(_crop_region_sync(blank_pdf, 1, descending, "png", dpi))

    assert asc_dims == desc_dims


def test_degenerate_bbox_raises_value_error(blank_pdf: Path) -> None:
    """A zero-area bbox raises ValueError (route maps it to 4xx, not 500)."""
    with pytest.raises(ValueError, match="degenerate bbox"):
        _crop_region_sync(blank_pdf, 1, [100.0, 100.0, 100.0, 400.0], "png", 300)


def test_wrong_arity_raises_value_error(blank_pdf: Path) -> None:
    with pytest.raises(ValueError, match="bbox must be"):
        _crop_region_sync(blank_pdf, 1, [1.0, 2.0, 3.0], "png", 300)
