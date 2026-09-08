"""MCP get_crop / get_page_image: lazy crop generation + dpi plumbing.

Parity with the CLI (`anchor crop` / `anchor page-image --dpi`) and the HTTP
crops / page-image routes: the same core read-op backs all three adapters.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)


@pytest.fixture()
def wired(tmp_path):
    store = FsDocStore(tmp_path)
    (store.bronze / "demo.pdf").write_bytes(b"%PDF-fake")
    silver_dir = store.silver / "demo"
    (silver_dir / "pages").mkdir(parents=True)
    (silver_dir / "index.json").write_text(
        json.dumps({
            "document": {"filename": "demo.pdf", "title": "Demo", "page_count": 1},
            "outline": [],
        }),
        encoding="utf-8",
    )
    (silver_dir / "pages" / "1.png").write_bytes(b"silver-150dpi-png")
    asyncio.run(store.write_gold_region_file("demo", 1, [
        {"id": "r1", "kind": "chart", "title": "Pump curve", "page": 1,
         "bbox": [10.0, 195.0, 200.0, 215.0], "tags": [], "entities": []},
    ]))
    renderer = FakePdfRenderer()
    ingest = IngestService(
        store,
        MemoryEventBus(),
        extractor=FakePdfExtractor(),
        renderer=renderer,
        polisher=FakePolisher(),
        region_extractor=FakeRegionExtractor(),
    )
    return ingest, store, renderer


def test_get_crop_generates_lazily_and_returns_path(wired):
    ingest, store, renderer = wired
    out = json.loads(asyncio.run(
        call_tool(ingest, store, "get_crop", {"slug": "demo", "rel_path": "1/r1.png"})
    ))
    assert out["format"] == "path"
    assert out["value"] == str(store.gold / "demo" / "pages" / "1" / "r1.png")
    assert (store.gold / "demo" / "pages" / "1" / "r1.png").exists()
    assert renderer.crop_calls[-1]["dpi"] == 300


def test_get_crop_accepts_inspect_region_token_and_dpi(wired):
    ingest, store, renderer = wired
    out = json.loads(asyncio.run(
        call_tool(ingest, store, "get_crop", {"slug": "demo", "rel_path": "p1/r1", "dpi": 600})
    ))
    assert out["format"] == "path"
    assert renderer.crop_calls[-1]["dpi"] == 600


def test_get_crop_unknown_region_reports_valid_form(wired):
    ingest, store, _renderer = wired
    out = json.loads(asyncio.run(
        call_tool(ingest, store, "get_crop", {"slug": "demo", "rel_path": "1/r9.png"})
    ))
    assert "r9" in out["error"]
    assert "<page>/<region_id>.png" in out["error"]


def test_get_page_image_dpi_renders_variant(wired):
    ingest, store, renderer = wired
    out = json.loads(asyncio.run(
        call_tool(ingest, store, "get_page_image", {"slug": "demo", "page": 1, "dpi": 600})
    ))
    assert out["value"] == str(store.silver / "demo" / "pages" / "1@600dpi.png")
    assert renderer.crop_calls[-1]["dpi"] == 600
    # Without dpi the stored silver image is served, no render.
    out = json.loads(asyncio.run(
        call_tool(ingest, store, "get_page_image", {"slug": "demo", "page": 1})
    ))
    assert out["value"] == str(store.silver / "demo" / "pages" / "1.png")
    assert len(renderer.crop_calls) == 1
