"""Existing adapter operations retain their shapes across derived collections."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.config import AnchorConfig
from tests.adapters.test_derive_region_parity import derive_via
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline
from tests.fixtures.tables import canonical_regions


def operation_via(transport, config, operation, *, locator=None, ref=None, success=True, status=200):
    cli_names = {"inspect": "inspect-region", "content": "region-content", "regions": "regions",
                 "map": "gold-map", "remove": "remove-region", "resolve": "resolve-ref"}
    mcp_names = {"inspect": "inspect_region", "content": "get_region_content", "regions": "get_gold_regions",
                 "map": "get_gold_map", "remove": "remove_region", "resolve": "resolve_source_ref"}
    if transport == "cli":
        args = [cli_names[operation], "doc"]
        if locator:
            args.append(locator)
        if ref:
            args.extend(["--ref", json.dumps(ref)])
        result = CliRunner().invoke(cli_app, [*args, "--data-dir", str(config.data_dir)])
        assert (result.exit_code == 0) == success, result.output
        return json.loads(result.stdout) if success else result.output
    runtime = build_project_runtime(config, profile=RuntimeProfile.INGEST)
    if transport == "http":
        app = build_app(workspace_service=runtime.workspace, doc_store=runtime.doc_store,
                        bus=runtime.bus, ingest_service=IngestService(
                            runtime.doc_store, runtime.bus, extractor=object(), renderer=object(),
                        ))
        path = {"inspect": f"regions/{locator}", "content": f"region-content/{locator}",
                "regions": "regions", "map": "gold-map", "remove": f"regions/{locator}",
                "resolve": "resolve-ref"}[operation]
        with TestClient(app) as client:
            if operation == "remove":
                result = client.delete(f"/api/documents/doc/{path}")
            else:
                params = {"page": ref["page"], "region_id": ref["region_id"],
                          "row": ref["cell"]["row"], "col": ref["cell"]["col"]} if ref else None
                result = client.get(f"/api/documents/doc/{path}", params=params)
        assert result.status_code == status, result.text
        return result.json() if success else result.json().get("detail", "")
    server = build_mcp_server(bundle=runtime)

    async def invoke():
        arguments = {"slug": "doc"}
        if locator:
            arguments["region_id"] = locator
        if ref:
            arguments["ref"] = ref
        async with Client(server) as client:
            result = await client.call_tool(mcp_names[operation], arguments)
        return json.loads(result.content[0].text)

    result = asyncio.run(invoke())
    assert ("error" not in result) == success, result
    return result if success else result["error"]


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_knowledge_and_legacy_read_remove_and_precise_cells_across_adapters(tmp_path, transport):
    store = FsDocStore(tmp_path)
    service = pipeline(store, [["Source chart"]])
    asyncio.run(service.ingest_pdf(b"source", "doc.pdf"))
    original = asyncio.run(store.get_regions("doc"))["pages"][1]
    asyncio.run(store.write_gold_region_file("doc", 1, [*original, {
        "id": "legacy", "kind": "chart_series", "derived_from": "p1/r1",
        "title": "Legacy series", "content": "Legacy producer content", "series": [1, 2],
    }]))
    gold_path = tmp_path / "gold/doc/pages/1.regions.json"
    gold_before = gold_path.read_bytes()
    cells = canonical_regions([{
        "id": "cells", "kind": "table", "page": 1, "bbox": [20, 30, 200, 100],
        "cells": [{"row": 0, "col": 0, "text": "Pressure", "bbox": [20, 40, 100, 50]},
                  {"row": 0, "col": 1, "text": "42", "bbox": [110, 40, 130, 50]}],
    }], origin="top-left")[0]
    config = AnchorConfig(data_dir=tmp_path)
    out = derive_via(transport, config, "doc", "p1/r1", {
        "id": "new", "kind": "normalized_spec", "title": "Normalized specs",
        "content": "Producer content", "cells": cells["cells"],
        "table_topology": cells["table_topology"], "series": [3, 4],
        "source_ref": {"item_id": "p1-i0", "cell": {"row": 0, "col": 1}},
    })
    assert "knowledge" in out["path"]
    assert gold_path.read_bytes() == gold_before
    for locator, content, points in (("p1/new", "Producer content", [3, 4]),
                                     ("p1/legacy", "Legacy producer content", [1, 2])):
        inspected = operation_via(transport, config, "inspect", locator=locator)
        assert inspected["derived_from"] == "p1/r1"
        assert inspected["data"]["series"] == points
        assert operation_via(transport, config, "content", locator=locator)["content"] == content
    resolved = operation_via(transport, config, "resolve", ref={
        "page": 1, "region_id": "new", "cell": {"row": 0, "col": 1},
    })
    assert resolved["precision"] == "cell" and resolved["bbox"] == [110, 40, 130, 50]
    inspected = operation_via(transport, config, "inspect", locator="p1/new")
    assert inspected["stored_source_ref"]["cell"] == {"row": 0, "col": 1}
    for operation in ("regions", "map"):
        assert [r["id"] for r in operation_via(transport, config, operation)["pages"]["1"]] == [
            "r1", "legacy", "new",
        ]
    asyncio.run(store.write_embeddings("doc", {"embed_model": "fake", "dim": 1, "vectors": [
        {"page": 1, "region_id": rid, "text": rid, "vector": [1]} for rid in ("r1", "legacy", "new")
    ]}))
    assert operation_via(transport, config, "remove", locator="p1/new")["embeddings_removed"] == 1
    assert gold_path.read_bytes() == gold_before
    knowledge_path = tmp_path / "knowledge/doc/pages/1.regions.json"
    knowledge_before = knowledge_path.read_bytes()
    assert operation_via(transport, config, "remove", locator="p1/legacy")["embeddings_removed"] == 1
    assert knowledge_path.read_bytes() == knowledge_before
    assert [r["id"] for r in asyncio.run(FsDocStore(tmp_path).get_regions("doc"))["pages"][1]] == ["r1"]


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_knowledge_errors_keep_source_and_derived_records_unchanged(tmp_path, transport):
    store = FsDocStore(tmp_path)
    asyncio.run(pipeline(store, [["Source"]]).ingest_pdf(b"source", "doc.pdf"))
    config = AnchorConfig(data_dir=tmp_path)
    derive_via(transport, config, "doc", "p1/r1", {"id": "new", "kind": "calculated"})
    gold_path = tmp_path / "gold/doc/pages/1.regions.json"
    knowledge_path = tmp_path / "knowledge/doc/pages/1.regions.json"
    before = (gold_path.read_bytes(), knowledge_path.read_bytes())
    derive_via(transport, config, "doc", "p1/new", {
        "id": "bad", "kind": "calculated", "source_ref": {"page": 2},
    }, success=False, http_status=404)
    error = operation_via(transport, config, "remove", locator="p1/r1", success=False, status=409)
    assert "model-extracted" in error and "Traceback" not in error
    error = operation_via(transport, config, "remove", locator="p1/missing", success=False, status=404)
    assert "not found" in error and "Traceback" not in error
    assert (gold_path.read_bytes(), knowledge_path.read_bytes()) == before
