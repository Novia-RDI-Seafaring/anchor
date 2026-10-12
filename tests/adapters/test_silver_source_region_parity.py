"""Existing inspect/content/cell operations reconstruct full source on all adapters."""
from __future__ import annotations

import asyncio

import pytest

from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.config import AnchorConfig
from tests.adapters.test_knowledge_region_parity import operation_via
from tests.extensions.anchor_pdfs.test_silver_source_regions import (
    LONG_TEXT,
    ingest_lane,
    table_document,
    text_document,
)


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_original_full_text_inspect_shapes_across_adapters(tmp_path, transport):
    store = FsDocStore(tmp_path)
    asyncio.run(ingest_lane(store, tmp_path, text_document(), "text"))
    region_id = asyncio.run(store.get_source_regions("doc"))["pages"][1][0]["id"]
    config = AnchorConfig(data_dir=tmp_path)
    inspected = operation_via(transport, config, "inspect", locator=f"p1/{region_id}")
    content = operation_via(transport, config, "content", locator=f"p1/{region_id}")
    assert inspected["content"] == content["content"] == LONG_TEXT
    assert inspected["member_item_ids"] == ["p1-i0"]
    assert inspected["members"][0]["item_id"] == "p1-i0"
    assert content["source_ref"]["page"] == 1
    assert content["source_ref"]["region_id"] == region_id
    assert {"slug", "page", "region_id", "kind", "content", "cells", "source_ref"}.issubset(content)


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_original_table_subset_and_precise_cells_across_adapters(tmp_path, transport):
    store = FsDocStore(tmp_path)
    asyncio.run(ingest_lane(store, tmp_path, table_document(), "harness", regions=[{
        "id": "limits", "kind": "spec_block", "title": "Limits",
        "table_slice": {"candidate_id": "p1-i0", "rows": [1], "columns": [0, 1]},
    }]))
    config = AnchorConfig(data_dir=tmp_path)
    content = operation_via(transport, config, "content", locator="p1/limits")
    assert "80 C" in content["content"]
    assert "17 bar" not in content["content"]
    assert "2900 rpm" not in content["content"]
    assert {(cell["row"], cell["col"]) for cell in content["cells"]} == {(1, 0), (1, 1)}
    resolved = operation_via(transport, config, "resolve", ref={
        "slug": "doc", "page": 1, "region_id": "limits", "cell": {"row": 1, "col": 1},
    })
    assert resolved["precision"] == "cell"
    assert resolved["bbox"] == [70, 40, 120, 55]
