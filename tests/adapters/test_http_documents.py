from __future__ import annotations

import json

import pymupdf
from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from tests.fixtures.fakes import (
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)


def test_document_crop_route_renders_bbox_from_raw_pdf(tmp_path):
    store = FsDocStore(tmp_path)
    (store.bronze / "demo.pdf").write_bytes(b"%PDF-fake")
    silver_dir = store.silver / "demo"
    silver_dir.mkdir(parents=True)
    (silver_dir / "index.json").write_text(
        json.dumps({
            "document": {"filename": "demo.pdf", "title": "Demo", "page_count": 1},
            "outline": [],
        }),
        encoding="utf-8",
    )

    bus = MemoryEventBus()
    workspace = WorkspaceService(MemoryWorkspaceStore(), bus)
    ingest = IngestService(
        store,
        bus,
        extractor=FakePdfExtractor(),
        renderer=FakePdfRenderer(),
        polisher=FakePolisher(),
        region_extractor=FakeRegionExtractor(),
    )
    app = build_app(
        workspace_service=workspace,
        ingest_service=ingest,
        doc_store=store,
        bus=bus,
    )

    response = TestClient(app).get("/api/documents/demo/pages/1/crop?bbox=1,2,3,4&dpi=300")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"CROP-1-[1.0, 2.0, 3.0, 4.0]-png"


def _build_real_renderer_app(tmp_path, *, page_h: float = 841.9):
    """Wire the app with the real PymupdfPdfRenderer over a generated PDF.

    Mirrors the production path (gold bbox -> on-the-fly crop) so the route's
    error handling is exercised against PyMuPDF, not the fake renderer.
    """
    store = FsDocStore(tmp_path)
    pdf = pymupdf.open()
    pdf.new_page(width=595.3, height=page_h)
    pdf.save(store.bronze / "demo.pdf")
    pdf.close()

    silver_dir = store.silver / "demo"
    silver_dir.mkdir(parents=True)
    (silver_dir / "index.json").write_text(
        json.dumps({
            "document": {"filename": "demo.pdf", "title": "Demo", "page_count": 1},
            "outline": [],
        }),
        encoding="utf-8",
    )

    bus = MemoryEventBus()
    workspace = WorkspaceService(MemoryWorkspaceStore(), bus)
    ingest = IngestService(
        store,
        bus,
        extractor=FakePdfExtractor(),
        renderer=PymupdfPdfRenderer(),
        polisher=FakePolisher(),
        region_extractor=FakeRegionExtractor(),
    )
    return build_app(
        workspace_service=workspace,
        ingest_service=ingest,
        doc_store=store,
        bus=bus,
    )


def test_crop_route_ascending_y_bbox_returns_png_not_500(tmp_path):
    # The verified #171 repro: an ascending-y gold bbox that the old code turned
    # into an inverted PyMuPDF rect -> FzErrorArgument -> HTTP 500.
    app = _build_real_renderer_app(tmp_path)
    response = TestClient(app).get(
        "/api/documents/demo/pages/1/crop?bbox=309.7,377.3,594.3,629.2&dpi=300"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_crop_route_degenerate_bbox_is_4xx_not_500(tmp_path):
    app = _build_real_renderer_app(tmp_path)
    response = TestClient(app).get(
        "/api/documents/demo/pages/1/crop?bbox=100,100,100,400&dpi=300"
    )
    assert 400 <= response.status_code < 500, response.text


def _build_fake_renderer_app_with_gold(tmp_path):
    """App over FsDocStore + FakePdfRenderer with one gold region seeded."""
    import asyncio

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

    bus = MemoryEventBus()
    workspace = WorkspaceService(MemoryWorkspaceStore(), bus)
    renderer = FakePdfRenderer()
    ingest = IngestService(
        store,
        bus,
        extractor=FakePdfExtractor(),
        renderer=renderer,
        polisher=FakePolisher(),
        region_extractor=FakeRegionExtractor(),
    )
    app = build_app(
        workspace_service=workspace,
        ingest_service=ingest,
        doc_store=store,
        bus=bus,
    )
    return app, store, renderer


def test_crops_route_generates_missing_crop_lazily(tmp_path):
    app, store, renderer = _build_fake_renderer_app_with_gold(tmp_path)
    response = TestClient(app).get("/api/documents/demo/crops/1/r1.png")
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"CROP-1-")
    # Persisted at the canonical path so the next read is served from disk.
    assert (store.gold / "demo" / "pages" / "1" / "r1.png").exists()
    assert renderer.crop_calls[-1]["dpi"] == 300


def test_crops_route_dpi_param_rerenders(tmp_path):
    app, _store, renderer = _build_fake_renderer_app_with_gold(tmp_path)
    response = TestClient(app).get("/api/documents/demo/crops/1/r1.png?dpi=600")
    assert response.status_code == 200, response.text
    assert renderer.crop_calls[-1]["dpi"] == 600


def test_crops_route_unknown_region_is_404_with_guidance(tmp_path):
    app, _store, _renderer = _build_fake_renderer_app_with_gold(tmp_path)
    response = TestClient(app).get("/api/documents/demo/crops/1/r9.png")
    assert response.status_code == 404
    assert "r9" in response.json()["detail"]
    assert "<page>/<region_id>.png" in response.json()["detail"]


def test_page_image_route_dpi_param_renders_variant(tmp_path):
    app, store, renderer = _build_fake_renderer_app_with_gold(tmp_path)
    # Without dpi: the stored silver image, untouched.
    default = TestClient(app).get("/api/documents/demo/pages/1/image")
    assert default.status_code == 200
    assert default.content == b"silver-150dpi-png"
    # With dpi: rendered from bronze and cached as a variant.
    hi = TestClient(app).get("/api/documents/demo/pages/1/image?dpi=600")
    assert hi.status_code == 200
    assert hi.content.startswith(b"CROP-1-")
    assert renderer.crop_calls[-1]["dpi"] == 600
    assert (store.silver / "demo" / "pages" / "1@600dpi.png").exists()
