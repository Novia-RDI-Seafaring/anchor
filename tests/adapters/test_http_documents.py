from __future__ import annotations

import json

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
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
