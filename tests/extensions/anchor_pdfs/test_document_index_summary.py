"""The silver index is a map by default, not the document.

Table cell content dominates the index payload, so `get_index` strips it
unless the caller asks for it. These tests pin the default, the opt-in, and
that every adapter carries the same switch.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.extensions.anchor_pdfs.core.silver import project_index
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore

INDEX = {
    "document": {"filename": "demo.pdf", "title": "Demo", "page_count": 2},
    "outline": [{"level": 1, "title": "OPERATING DATA", "page": 1, "bbox": [0, 0, 1, 1]}],
    "tables": [
        {
            "id": "t1",
            "page": 1,
            "bbox": [0, 0, 10, 10],
            "caption": "OPERATING DATA",
            "shape": {"rows": 2, "cols": 2},
            "header_row": ["Max inlet pressure"],
            "first_column_values": ["LKH-5:"],
            "cells": [{"row": 0, "col": 0, "text": "Max inlet pressure", "bbox": [0, 0, 1, 1]}],
        },
        {
            "id": "t2",
            "page": 1,
            "bbox": [0, 20, 10, 30],
            "caption": "OPERATING DATA",
            "shape": {"rows": 3, "cols": 2},
            "header_row": ["Temperature"],
            "first_column_values": ["Flush media:"],
            "cells": [{"row": 0, "col": 0, "text": "Temperature", "bbox": [0, 0, 1, 1]}],
        },
    ],
    "figures": [{"page": 2, "bbox": [0, 0, 5, 5], "caption": "Flow chart"}],
}

IDENTITY_FIELDS = ("id", "page", "bbox", "caption", "shape", "header_row", "first_column_values")


def test_project_index_drops_cells_by_default():
    out = project_index(INDEX)
    assert [t.get("cells") for t in out["tables"]] == [None, None]


def test_project_index_keeps_every_identifying_field():
    out = project_index(INDEX)
    for table in out["tables"]:
        assert set(table) == set(IDENTITY_FIELDS)


def test_project_index_keeps_outline_figures_and_document():
    out = project_index(INDEX)
    assert out["document"] == INDEX["document"]
    assert out["outline"] == INDEX["outline"]
    assert out["figures"] == INDEX["figures"]


def test_same_caption_tables_stay_distinguishable_without_cells():
    # Eight tables on one page of the LKH datasheet share the caption
    # "OPERATING DATA"; header_row and first_column_values are what tell
    # them apart, so a map without cells is still usable for choosing one.
    tables = project_index(INDEX)["tables"]
    assert tables[0]["caption"] == tables[1]["caption"]
    assert tables[0]["header_row"] != tables[1]["header_row"]


def test_project_index_include_content_returns_the_full_record():
    assert project_index(INDEX, include_content=True) == INDEX


def test_project_index_does_not_mutate_its_input():
    before = json.dumps(INDEX, sort_keys=True)
    project_index(INDEX)
    assert json.dumps(INDEX, sort_keys=True) == before


def test_project_index_passes_none_through():
    assert project_index(None) is None


def test_project_index_tolerates_a_malformed_index():
    assert project_index({"tables": "nope"})["tables"] == "nope"
    assert project_index({"tables": [None, 3]})["tables"] == [None, 3]
    assert project_index({})== {}


def test_fs_store_strips_cells_by_default_and_restores_them_on_request(tmp_path):
    store = FsDocStore(tmp_path)

    async def run():
        await store.write_silver_artifact("demo", "index.json", json.dumps(INDEX))
        default = await store.get_index("demo")
        full = await store.get_index("demo", include_content=True)
        assert "cells" not in default["tables"][0]
        assert full == INDEX
        assert len(json.dumps(default)) < len(json.dumps(full))

    asyncio.run(run())


def test_memory_store_strips_cells_by_default():
    store = MemoryDocStore()

    async def run():
        await store.write_silver_artifact("demo", "index.json", json.dumps(INDEX))
        default = await store.get_index("demo")
        full = await store.get_index("demo", include_content=True)
        assert "cells" not in default["tables"][0]
        assert full == INDEX

    asyncio.run(run())


def test_missing_index_is_still_reported_as_missing(tmp_path):
    store = FsDocStore(tmp_path)
    assert asyncio.run(store.get_index("nope")) is None
    assert asyncio.run(store.get_index("nope", include_content=True)) is None


def test_mcp_tool_advertises_the_switch():
    from anchor.extensions.anchor_pdfs.mcp_tool_definitions import tool_definitions

    tool = next(t for t in tool_definitions() if t["name"] == "get_document_index")
    props = tool["inputSchema"]["properties"]
    assert "include_content" in props
    assert props["include_content"]["type"] == "boolean"
    assert "include_content" not in tool["inputSchema"]["required"]


def test_mcp_handler_defaults_to_the_map_and_honours_the_flag():
    from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services()
    store = services.doc_store

    async def run():
        await store.write_silver_artifact("demo", "index.json", json.dumps(INDEX))
        default = json.loads(
            await call_tool(services.ingest, store, "get_document_index", {"slug": "demo"})
        )
        full = json.loads(
            await call_tool(
                services.ingest,
                store,
                "get_document_index",
                {"slug": "demo", "include_content": True},
            )
        )
        assert "cells" not in default["tables"][0]
        assert full == INDEX

    asyncio.run(run())


def test_http_route_defaults_to_the_map_and_honours_the_query_param():
    from fastapi.testclient import TestClient

    from anchor.adapters.http.app import build_app
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services()
    asyncio.run(
        services.doc_store.write_silver_artifact("demo", "index.json", json.dumps(INDEX))
    )
    app = build_app(
        workspace_service=services.workspace,
        ingest_service=services.ingest,
        doc_store=services.doc_store,
        bus=services.bus,
    )
    client = TestClient(app)

    default = client.get("/api/documents/demo/index").json()
    full = client.get("/api/documents/demo/index?include_content=true").json()
    assert "cells" not in default["tables"][0]
    assert full == INDEX


@pytest.mark.parametrize("flag,has_cells", [([], False), (["--include-content"], True)])
def test_cli_index_flag(tmp_path, flag, has_cells):
    import typer
    from typer.testing import CliRunner

    from anchor.adapters.cli.documents import register_document_commands

    store = FsDocStore(tmp_path)
    asyncio.run(store.write_silver_artifact("demo", "index.json", json.dumps(INDEX)))

    app = typer.Typer()
    register_document_commands(app)
    result = CliRunner().invoke(app, ["index", "demo", "--data-dir", str(tmp_path), *flag])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert ("cells" in payload["tables"][0]) is has_cells


def test_bbox_migration_preserves_table_cells():
    # migrate_document is a read-modify-write of index.json. If it reads the
    # default map form and writes that back, every table's cell content is
    # deleted from disk -- and a running serve migrates on start, so the loss
    # would be silent and immediate. Lock the full read in.
    from anchor.extensions.anchor_pdfs.core.bbox_migration import migrate_document
    from tests.core.test_bbox_migration import _seed_legacy
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services(page_count=1)
    _seed_legacy(services.doc_store)

    async def run():
        result = await migrate_document(services.doc_store, None, "doc")
        assert result["status"] == "migrated"
        after = await services.doc_store.get_index("doc", include_content=True)
        assert after["tables"][0]["cells"], "migration erased table cells"

    asyncio.run(run())
