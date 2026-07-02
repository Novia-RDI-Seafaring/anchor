"""Opt-in full-page OCR + low-text-page warning (issue #231).

Unit-level seams only: no real docling / GPU / model. Covers
- ``_build_pipeline_options`` sets force_full_page_ocr only when asked;
- ``find_low_text_pages`` / ``low_text_pages_warning`` flag no-text pages;
- the ``full_page_ocr`` flag reaches ``extractor.extract`` via IngestService;
- the MCP ingest_pdf schema exposes ``full_page_ocr``.
"""
from __future__ import annotations

import asyncio

import pytest

from anchor.extensions.anchor_pdfs.core.silver import (
    LOW_TEXT_CHAR_THRESHOLD,
    find_low_text_pages,
    low_text_pages_warning,
)

# ── _build_pipeline_options: force_full_page_ocr only when requested ──────────


def _rapid_ocr_available() -> bool:
    try:
        import docling.datamodel.pipeline_options  # noqa: F401
    except Exception:  # noqa: BLE001 - docling optional in some envs
        return False
    return True


@pytest.mark.skipif(not _rapid_ocr_available(), reason="docling not installed")
def test_build_pipeline_options_default_no_full_page_ocr():
    from anchor.extensions.anchor_pdfs.infra.pdf import docling_extractor as dx

    opts = dx._build_pipeline_options("cpu")
    assert opts.ocr_options.force_full_page_ocr is False


@pytest.mark.skipif(not _rapid_ocr_available(), reason="docling not installed")
def test_build_pipeline_options_full_page_ocr_when_requested():
    from anchor.extensions.anchor_pdfs.infra.pdf import docling_extractor as dx

    opts = dx._build_pipeline_options("cpu", full_page_ocr=True)
    assert opts.ocr_options.force_full_page_ocr is True
    # The onnxruntime backend pin is preserved regardless of the OCR mode.
    assert getattr(opts.ocr_options, "backend", "onnxruntime") == "onnxruntime"


# ── low-text-page detection helper ───────────────────────────────────────────


def test_find_low_text_pages_flags_pages_with_no_text():
    docling = {
        "items": [
            {"label": "text", "text": "A" * 200, "page": 1, "bbox": []},
            # Page 2 has an item but effectively no characters (whitespace only).
            {"label": "text", "text": "   \n  ", "page": 2, "bbox": []},
            # Page 3 emitted nothing at all — must still be caught via page_count.
        ],
    }
    assert find_low_text_pages(docling, page_count=3) == [2, 3]


def test_find_low_text_pages_counts_table_cell_text():
    # A page whose only text lives in table cells is NOT low-text.
    docling = {
        "items": [
            {
                "label": "table",
                "text": "",
                "page": 1,
                "bbox": [],
                "cells": [{"row": 0, "col": 0, "text": "cell value here " * 3}],
            },
        ],
    }
    assert find_low_text_pages(docling, page_count=1) == []


def test_find_low_text_pages_normal_pages_not_flagged():
    docling = {
        "items": [
            {"label": "text", "text": "Real dense paragraph text." * 5, "page": 1, "bbox": []},
            {"label": "text", "text": "Another dense page of content." * 5, "page": 2, "bbox": []},
        ],
    }
    assert find_low_text_pages(docling, page_count=2) == []


def test_find_low_text_pages_empty_doc_returns_empty():
    assert find_low_text_pages({"items": []}, page_count=0) == []


def test_threshold_boundary():
    # Exactly threshold chars is NOT flagged; one below is.
    at = {"items": [{"label": "text", "text": "x" * LOW_TEXT_CHAR_THRESHOLD, "page": 1}]}
    below = {"items": [{"label": "text", "text": "x" * (LOW_TEXT_CHAR_THRESHOLD - 1), "page": 1}]}
    assert find_low_text_pages(at, page_count=1) == []
    assert find_low_text_pages(below, page_count=1) == [1]


def test_low_text_warning_names_pages_and_remedy():
    msg = low_text_pages_warning([2, 3])
    assert msg is not None
    assert "2, 3" in msg
    assert "Pages" in msg  # plural
    assert "--full-page-ocr" in msg
    assert "full_page_ocr=true" in msg


def test_low_text_warning_singular_and_none():
    assert low_text_pages_warning([]) is None
    single = low_text_pages_warning([4])
    assert single is not None
    assert single.startswith("Page 4 ")


# ── flag plumbing: ingest_pdf(full_page_ocr=True) reaches extract(...) ────────


def test_full_page_ocr_flag_reaches_extractor(tmp_path):
    from anchor.core.clock import FixedClock
    from anchor.extensions.anchor_pdfs.core.services import IngestService
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from tests.fixtures.fakes import (
        FakePdfExtractor,
        FakePdfRenderer,
        FakePolisher,
        FakeRegionExtractor,
    )

    extractor = FakePdfExtractor()

    async def run():
        store = FsDocStore(tmp_path)
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=extractor,
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=FakeRegionExtractor(),
            clock=FixedClock(ts=1700000000.0),
        )
        await ingest.ingest_pdf(b"%PDF-1.4", "doc.pdf", full_page_ocr=True)

    asyncio.run(run())
    assert extractor.calls, "extract was never called"
    assert extractor.calls[0]["full_page_ocr"] is True


def test_full_page_ocr_defaults_false(tmp_path):
    from anchor.core.clock import FixedClock
    from anchor.extensions.anchor_pdfs.core.services import IngestService
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from tests.fixtures.fakes import (
        FakePdfExtractor,
        FakePdfRenderer,
        FakePolisher,
        FakeRegionExtractor,
    )

    extractor = FakePdfExtractor()

    async def run():
        store = FsDocStore(tmp_path)
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=extractor,
            renderer=FakePdfRenderer(page_count=1),
            polisher=FakePolisher(),
            region_extractor=FakeRegionExtractor(),
            clock=FixedClock(ts=1700000000.0),
        )
        await ingest.ingest_pdf(b"%PDF-1.4", "doc.pdf")

    asyncio.run(run())
    assert extractor.calls[0]["full_page_ocr"] is False


# ── warning surfaces in the ingest summary ───────────────────────────────────


def test_low_text_warning_surfaces_in_summary(tmp_path):
    from anchor.core.clock import FixedClock
    from anchor.extensions.anchor_pdfs.core.services import IngestService
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from tests.fixtures.fakes import (
        FakePdfExtractor,
        FakePdfRenderer,
        FakePolisher,
        FakeRegionExtractor,
    )

    # Two pages; page 2 has no extractable text.
    extractor = FakePdfExtractor({
        "items": [
            {"label": "text", "text": "Dense real content." * 5, "page": 1, "bbox": []},
            {"label": "text", "text": "  ", "page": 2, "bbox": []},
        ],
    })

    async def run():
        store = FsDocStore(tmp_path)
        ingest = IngestService(
            store,
            MemoryEventBus(),
            extractor=extractor,
            renderer=FakePdfRenderer(page_count=2),
            polisher=FakePolisher(),
            region_extractor=FakeRegionExtractor(),
            clock=FixedClock(ts=1700000000.0),
        )
        return await ingest.ingest_pdf(b"%PDF-1.4", "doc.pdf")

    summary = asyncio.run(run())
    warnings = summary.get("warnings", [])
    assert warnings, "expected a low-text warning in the summary"
    assert "--full-page-ocr" in warnings[0]
    assert "2" in warnings[0]


# ── MCP schema exposes full_page_ocr ─────────────────────────────────────────


def test_mcp_ingest_pdf_schema_has_full_page_ocr():
    from anchor.extensions.anchor_pdfs.mcp_handlers import tool_definitions

    defs = {d["name"]: d for d in tool_definitions()}
    props = defs["ingest_pdf"]["inputSchema"]["properties"]
    assert "full_page_ocr" in props
    assert props["full_page_ocr"]["type"] == "boolean"
