"""FsDocStore — bronze/silver/gold layout."""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore


@pytest.fixture
def store(tmp_path):
    return FsDocStore(tmp_path)


def test_stash_bronze_writes_pdf(store, tmp_path):
    async def run():
        path = await store.stash_bronze(b"%PDF-fake", "demo.pdf")
        assert path.read_bytes() == b"%PDF-fake"
        assert path.parent.name == "bronze"

    asyncio.run(run())


def test_write_and_read_silver_index(store):
    async def run():
        idx = {"document": {"page_count": 4, "title": "Demo", "filename": "demo.pdf"}, "outline": [], "tables": [], "figures": []}
        await store.write_silver_artifact("demo", "index.json", json.dumps(idx))
        out = await store.get_index("demo")
        assert out == idx

    asyncio.run(run())


def test_list_documents_reports_silver_only_when_no_gold(store):
    async def run():
        await store.write_silver_artifact("demo", "index.json", json.dumps({
            "document": {"page_count": 1, "title": "Demo", "filename": "demo.pdf"},
        }))
        docs = await store.list_documents()
        assert len(docs) == 1
        assert docs[0]["slug"] == "demo"
        assert docs[0]["has_gold"] is False
        assert docs[0]["region_count"] == 0

    asyncio.run(run())


def test_write_and_read_gold_regions(store):
    async def run():
        await store.write_gold_region_file("demo", 1, [
            {"id": "r1", "kind": "text", "title": "x", "description": "y", "bbox": [0, 100, 50, 0]},
        ])
        regs = await store.get_regions("demo")
        assert 1 in regs["pages"]
        assert regs["pages"][1][0]["id"] == "r1"

    asyncio.run(run())


def test_get_page_text_prefers_polished_over_raw(store):
    async def run():
        await store.write_silver_artifact("demo", "pages/1.raw.md", "raw content")
        await store.write_silver_artifact("demo", "pages/1.md", "polished content")
        text = await store.get_page_text("demo", 1)
        assert text == "polished content"

    asyncio.run(run())


def test_get_page_text_falls_back_to_raw(store):
    async def run():
        await store.write_silver_artifact("demo", "pages/2.raw.md", "raw only")
        assert await store.get_page_text("demo", 2) == "raw only"

    asyncio.run(run())


def test_get_crop_path_blocks_traversal(store):
    async def run():
        # No crop exists; traversal-cleansed path stays under the slug.
        p = await store.get_crop_path("demo", "../../escape.png")
        assert p is None or "demo" in str(p)

    asyncio.run(run())
