"""Silver geometry travels with the document index without requiring gold."""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline
from tests.fixtures.fakes import FakePdfExtractor


META = {"bbox_origin": "top-left", "pages": {
    "1": {"page_size": [600, 800], "items": [{"text": "private content"}]},
}}
SUMMARY = {"bbox_origin": "top-left", "pages": {"1": {"page_size": [600, 800]}}}


@pytest.mark.parametrize("memory", [False, True])
def test_silver_only_index_geometry_is_compact_and_preserves_origin(tmp_path, memory):
    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        await store.write_silver_artifact("doc", "index.json", json.dumps({"document": {"page_count": 1}}))
        await store.write_silver_artifact("doc", "pages.meta.json", json.dumps(META))
        assert await store.get_gold_map("doc") is None
        for content in (False, True):
            assert (await store.get_index("doc", include_content=content))["pages_meta"] == SUMMARY
        assert await store.get_pages_meta("doc") == META
        bottom_left = {**META, "bbox_origin": "bottom-left"}
        await store.write_silver_artifact("doc", "pages.meta.json", json.dumps(bottom_left))
        assert (await store.get_index("doc"))["pages_meta"]["bbox_origin"] == "bottom-left"
    asyncio.run(run())


@pytest.mark.parametrize("memory", [False, True])
def test_index_geometry_is_pinned_to_replacement_generation(tmp_path, memory):
    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        def local(size, pages):
            extractor = FakePdfExtractor({"coord_origin": "top-left",
                "pages": {p: {"width": size[0], "height": size[1]} for p in range(1, len(pages) + 1)},
                "items": [{"label": "text", "text": "source", "page": p, "bbox": [60, 100, 240, 150]}
                          for p in range(1, len(pages) + 1)]})
            svc = pipeline(store, pages, extractor=extractor)
            svc.region_extractor = None
            return svc
        await local([600, 800], [["old"], ["removed"]]).ingest_pdf(b"A", "doc.pdf")
        old = store.snapshot("doc")
        assert await store.get_gold_map("doc") is None
        await local([1200, 1600], [["new"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        current = await store.get_index("doc")
        assert current["pages_meta"]["pages"] == {"1": {"page_size": [1200.0, 1600.0]}}
        assert (await old.get_index("doc"))["pages_meta"]["pages"]["1"]["page_size"] == [600, 800]
        assert "2" in (await old.get_index("doc"))["pages_meta"]["pages"]
        assert await store.get_gold_map("doc") is None
    asyncio.run(run())


def test_existing_index_adapters_include_silver_geometry(tmp_path):
    from fastapi.testclient import TestClient
    import typer
    from typer.testing import CliRunner

    from anchor.adapters.cli.documents import register_document_commands
    from anchor.adapters.http.app import build_app
    from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services()
    async def seed(store):
        await store.write_silver_artifact("doc", "index.json", json.dumps({"document": {"page_count": 1}}))
        await store.write_silver_artifact("doc", "pages.meta.json", json.dumps(META))
    asyncio.run(seed(services.doc_store))
    app = build_app(workspace_service=services.workspace, ingest_service=services.ingest,
                    doc_store=services.doc_store, bus=services.bus)
    assert TestClient(app).get("/api/documents/doc/index").json()["pages_meta"] == SUMMARY
    result = asyncio.run(call_tool(services.ingest, services.doc_store, "get_document_index", {"slug": "doc"}))
    assert json.loads(result)["pages_meta"] == SUMMARY
    asyncio.run(seed(FsDocStore(tmp_path)))
    cli = typer.Typer()
    register_document_commands(cli)
    result = CliRunner().invoke(cli, ["index", "doc", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["pages_meta"] == SUMMARY
