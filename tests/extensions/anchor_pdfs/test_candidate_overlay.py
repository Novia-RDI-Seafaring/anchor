"""Candidate debug images preserve source pixels and canonical geometry."""
from __future__ import annotations

import asyncio
import json

import pymupdf
import pytest

from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.core.silver import build_page_candidates, normalize_items
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_session_store import MemoryIngestSessionStore
from anchor.extensions.anchor_pdfs.infra.pdf.candidate_overlay import render_candidate_overlay
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import FakePdfExtractor


def _page_image(dpi=72):
    with pymupdf.open() as document:
        page = document.new_page(width=120, height=200)
        page.draw_rect(pymupdf.Rect(100, 180, 110, 190), fill=(0, 0, 0))
        return page.get_pixmap(dpi=dpi).tobytes("png")


@pytest.mark.parametrize("dpi", [72, 150, 300])
def test_overlay_scales_top_left_boxes_to_actual_raster_dimensions(dpi):
    original = _page_image(dpi)
    overlay = render_candidate_overlay(original, [
        {"id": "p1-i0", "label": "text", "bbox": [20, 50, 70, 80]},
    ], page_size=(120, 200))
    base, annotated = pymupdf.Pixmap(original), pymupdf.Pixmap(overlay)
    assert (annotated.width, annotated.height) == (base.width, base.height)
    scale_x, scale_y = base.width / 120, base.height / 200
    edge = round(20 * scale_x), round(65 * scale_y)
    assert annotated.pixel(*edge)[:3] != base.pixel(*edge)[:3]
    assert annotated.pixel(edge[0], round(135 * scale_y))[:3] == (255, 255, 255)
    # The source marker is outside the candidate and remains unchanged.
    marker = round(105 * scale_x), round(185 * scale_y)
    assert annotated.pixel(*marker)[:3] == base.pixel(*marker)[:3] == (0, 0, 0)


def test_overlay_uses_independent_axis_scales_and_label_colors(monkeypatch):
    labels = []
    insert_text = pymupdf.Page.insert_text

    def record_text(page, point, text, *args, **kwargs):
        labels.append(text)
        return insert_text(page, point, text, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "insert_text", record_text)
    overlay = render_candidate_overlay(_page_image(), [
        {"id": "p1-i0", "label": "text", "bbox": [40, 150, 140, 240], "reading_order": 4},
        {"id": "p1-i1", "label": "table", "bbox": [40, 330, 140, 420]},
    ], page_size=(240, 600))
    annotated = pymupdf.Pixmap(overlay)
    text_color = annotated.pixel(20, 65)[:3]
    table_color = annotated.pixel(20, 125)[:3]
    assert text_color != table_color
    assert text_color != (255, 255, 255) != table_color
    assert labels == ["p1-i0 text order=4", "p1-i1 table"]


@pytest.mark.parametrize("bbox", [[], None, [0, 1, 2], [0, None, 2, 3], [0, float("nan"), 2, 3]])
def test_malformed_boxes_are_diagnosed_without_losing_the_page(bbox, monkeypatch):
    labels = []
    insert_text = pymupdf.Page.insert_text

    def record_text(page, point, text, *args, **kwargs):
        labels.append(text)
        return insert_text(page, point, text, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "insert_text", record_text)
    overlay = render_candidate_overlay(_page_image(), [
        {"id": "p1-i0", "label": "text", "bbox": bbox},
    ], page_size=(120, 200))
    assert labels == ["p1-i0 text: no usable bbox"]
    assert pymupdf.Pixmap(overlay).pixel(105, 185)[:3] == (0, 0, 0)


def test_missing_geometry_is_visible_without_guessing_a_dpi():
    overlay = render_candidate_overlay(_page_image(), [
        {"id": "p1-i0", "label": "text", "bbox": [20, 50, 70, 80]},
    ], page_size=None)
    annotated = pymupdf.Pixmap(overlay)
    assert annotated.pixel(20, 65)[:3] == (255, 255, 255)
    assert any(annotated.pixel(x, y)[:3] != (255, 255, 255)
               for x in range(120) for y in range(25))


def test_empty_candidates_preserve_the_source_image():
    original = _page_image()
    overlay = render_candidate_overlay(original, [], page_size=(120, 200))
    assert pymupdf.Pixmap(overlay).samples == pymupdf.Pixmap(original).samples


@pytest.mark.parametrize("mode", ["keyed", "text", "harness"])
def test_ingest_writes_overlays_next_to_unchanged_page_and_candidates(tmp_path, mode):
    with pymupdf.open() as document:
        document.new_page(width=120, height=200)
        document.new_page(width=200, height=120)
        pdf_bytes = document.tobytes()
    docling = {
        "coord_origin": "top-left",
        "pages": {1: {"width": 120, "height": 200}, 2: {"width": 200, "height": 120}},
        "items": [
            {"label": "text", "text": "Source one", "page": 1,
             "bbox": [20, 50, 70, 80], "reading_order": 4},
            {"label": "table", "text": "Source two", "page": 2,
             "bbox": [20, 50, 70, 80], "reading_order": 8},
        ],
    }

    async def run():
        store = FsDocStore(tmp_path)
        renderer = PymupdfPdfRenderer()
        extractor = FakePdfExtractor(docling)
        if mode == "harness":
            service = IngestSessionService(
                store, MemoryIngestSessionStore(), MemoryEventBus(),
                extractor=extractor, renderer=renderer,
            )
            await service.ingest_begin(pdf_bytes, "source.pdf")
        else:
            service = IngestService(store, MemoryEventBus(), extractor=extractor, renderer=renderer)
            await service.ingest_pdf(pdf_bytes, "source.pdf", profile=mode, regions=mode == "text")
        source_images = await renderer.render_pages(await store.get_raw_pdf_path("source"), dpi=150)
        expected = build_page_candidates(normalize_items(docling))
        for page in (1, 2):
            directory = tmp_path / "silver/source/pages"
            assert (directory / f"{page}.png").read_bytes() == source_images[page]
            actual = json.loads((directory / f"{page}.candidates.json").read_text(encoding="utf-8"))
            assert actual == expected[page]
            base = pymupdf.Pixmap(source_images[page])
            overlay = pymupdf.Pixmap((directory / f"{page}.candidates.png").read_bytes())
            assert (overlay.width, overlay.height) == (base.width, base.height)
            assert overlay.samples != base.samples

    asyncio.run(run())
