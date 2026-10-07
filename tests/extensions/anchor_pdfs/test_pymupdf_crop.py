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
from xml.etree import ElementTree

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


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
def test_degenerate_bbox_raises_value_error(blank_pdf: Path, fmt: str) -> None:
    """A zero-area bbox raises ValueError (route maps it to 4xx, not 500)."""
    with pytest.raises(ValueError, match="degenerate bbox"):
        _crop_region_sync(blank_pdf, 1, [100.0, 100.0, 100.0, 400.0], fmt, 300)


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
def test_wrong_arity_raises_value_error(blank_pdf: Path, fmt: str) -> None:
    with pytest.raises(ValueError, match="bbox must be"):
        _crop_region_sync(blank_pdf, 1, [1.0, 2.0, 3.0], fmt, 300)


@pytest.mark.parametrize("dpi", [72, 144, 200])
def test_svg_viewbox_uses_region_dimensions(blank_pdf: Path, dpi: int) -> None:
    bbox = [56.4, 58.5, 291.0, 188.7]
    svg = ElementTree.fromstring(_crop_region_sync(blank_pdf, 1, bbox, "svg", dpi))
    expected = [(bbox[2] - bbox[0]) * dpi / 72, (bbox[3] - bbox[1]) * dpi / 72]

    assert [float(value) for value in svg.attrib["viewBox"].split()] == pytest.approx(
        [0, 0, *expected]
    )
    assert [float(svg.attrib[key]) for key in ("width", "height")] == pytest.approx(expected)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("cropbox", [None, (20, 30, 380, 560)])
@pytest.mark.parametrize("dpi", [72, 144])
def test_svg_visible_content_matches_png_crop(
    tmp_path: Path, rotation: int, cropbox: tuple[int, int, int, int] | None, dpi: int
) -> None:
    path = tmp_path / "regions.pdf"
    source_bbox = pymupdf.Rect(80, 100, 180, 150)
    with pymupdf.open() as doc:
        other = doc.new_page(width=400, height=600)
        other.draw_rect(other.rect, color=None, fill=(0, 0, 1))
        page = doc.new_page(width=400, height=600)
        for rect, color in (
            (source_bbox, (1, 0, 0)),
            (pymupdf.Rect(80, 100, 100, 115), (0, 1, 0)),
            (pymupdf.Rect(200, 200, 240, 240), (0, 0, 1)),
        ):
            page.draw_rect(rect, color=None, fill=color)
        if cropbox is not None:
            page.set_cropbox(cropbox)
        page.set_rotation(rotation)
        origin = page.cropbox_position
        bbox = source_bbox - (origin.x, origin.y, origin.x, origin.y)
        bbox *= page.rotation_matrix
        doc.save(path)
    original = path.read_bytes()

    svg = _crop_region_sync(path, 2, list(bbox), "svg", dpi)
    png = _crop_region_sync(path, 2, list(bbox), "png", dpi)
    with pymupdf.open(stream=svg, filetype="svg") as doc:
        pix = doc[0].get_pixmap(dpi=72)

    assert (pix.width, pix.height) == _png_dims(png) == (
        int(bbox.width * dpi / 72), int(bbox.height * dpi / 72)
    )
    assert pix.samples == pymupdf.Pixmap(png).samples
    assert pix.pixel(pix.width // 2, pix.height // 2) == (255, 0, 0)
    assert b"\x00\xff\x00" in pix.samples
    assert path.read_bytes() == original

    reversed_bbox = [bbox.x1, bbox.y1, bbox.x0, bbox.y0]
    assert _crop_region_sync(path, 2, reversed_bbox, "svg", dpi) == svg


def test_svg_crop_clips_to_visible_page(blank_pdf: Path) -> None:
    bbox = [-10, -20, 100, 100]
    svg = _crop_region_sync(blank_pdf, 1, bbox, "svg", 72)
    with pymupdf.open(stream=svg, filetype="svg") as doc:
        pix = doc[0].get_pixmap(dpi=72)
    assert (pix.width, pix.height) == _png_dims(
        _crop_region_sync(blank_pdf, 1, bbox, "png", 72)
    ) == (100, 100)


def test_svg_crop_outside_page_raises_value_error(blank_pdf: Path) -> None:
    with pytest.raises(ValueError, match="does not intersect the page"):
        _crop_region_sync(blank_pdf, 1, [1000, 1000, 1100, 1100], "svg", 72)
