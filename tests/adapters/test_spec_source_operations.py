"""Create and update use one evidence contract through real adapter operations."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from mcp.types import CallToolRequest, CallToolRequestParams
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.infra.config import AnchorConfig
from tests.adapters.test_value_provenance_parity import _input, _regions
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline
from tests.fixtures.tables import canonical_regions


class CanvasOperations:
    """Exercise transport entry points and read back persisted state."""

    def __init__(self, transport, config, workspace="g6"):
        self.transport, self.config, self.slug = transport, config, workspace
        self.runtime = build_project_runtime(config, profile=RuntimeProfile.CANVAS)
        self.http = TestClient(build_app(
            workspace_service=self.runtime.workspace, doc_store=self.runtime.doc_store,
            bus=self.runtime.bus, ingest_service=IngestService(
                self.runtime.doc_store, self.runtime.bus, extractor=object(), renderer=object(),
            ),
        ))
        self.mcp = build_mcp_server(bundle=self.runtime)

    def call(self, operation, data, node_id=None):
        args = {"data": deepcopy(data)}
        if operation == "add":
            args.update(node_type="spec", label="Evidence parity")
        if self.transport == "http":
            url = f"/api/workspaces/{self.slug}/nodes"
            response = (self.http.post(url, json=args) if operation == "add" else
                        self.http.patch(f"{url}/{node_id}", json=args))
            assert response.status_code == (201 if operation == "add" else 200), response.text
            out = response.json()
        elif self.transport == "mcp":
            async def invoke():
                result = await self.mcp.request_handlers[CallToolRequest](CallToolRequest(
                    method="tools/call", params=CallToolRequestParams(
                        name=f"canvas_{operation}_node", arguments={
                            "workspace_slug": self.slug, **args,
                            **({"id": node_id} if node_id else {}),
                        },
                    ),
                ))
                return json.loads(result.root.content[0].text)
            out = asyncio.run(invoke())
            assert "error" not in out, out
        else:
            command = ["canvas", f"{operation}-node", self.slug,
                       "spec" if operation == "add" else node_id,
                       "--data", json.dumps(data), "--data-dir", str(self.config.data_dir)]
            result = CliRunner().invoke(cli_app, command)
            assert result.exit_code == 0, result.output
            # Click's output mixes stderr progress with the JSON stdout stream.
            out = json.loads(result.stdout)
        return out["event"]["payload"]["id"]

    def read(self, node_id):
        fresh = build_project_runtime(self.config, profile=RuntimeProfile.CANVAS)
        state = asyncio.run(fresh.workspace.get_state(self.slug))
        return next(n["data"] for n in state["nodes"] if n["id"] == node_id)


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_create_and_update_same_coarse_ref_are_equally_precise(transport, tmp_path):
    ops = CanvasOperations(transport, AnchorConfig(data_dir=tmp_path))
    asyncio.run(ops.runtime.workspace.create_workspace("g6"))
    asyncio.run(ops.runtime.doc_store.write_gold_region_file("doc", 1, _regions()))
    data = _input("exact")
    node_id = ops.call("add", data)
    created = ops.read(node_id)
    ops.call("update", data, node_id)
    updated = ops.read(node_id)
    assert created == updated
    assert created["rows"][0]["source_ref"]["bbox"] == [60, 50, 90, 60]


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("case", [
    "precise", "missing", "wrong_key", "wrong_value", "conflicting_bbox",
    "inferred", "ambiguous", "uncertified", "missing_cells", "malformed",
    "ambiguous_topology", "no_scope", "empty_store", "unknown_origin", "new_origin",
])
def test_create_update_strict_evidence_matrix(transport, reverse, case, tmp_path):
    ops = CanvasOperations(transport, AnchorConfig(data_dir=tmp_path))
    asyncio.run(ops.runtime.workspace.create_workspace("g6"))
    regions = _regions(repeated=case == "ambiguous")
    data = _input(case if case in {
        "missing", "wrong_key", "wrong_value", "conflicting_bbox", "inferred", "ambiguous",
    } else "exact")
    ref = data["rows"][0]["source_ref"]
    if case == "precise":
        ref.update(bbox=[60, 50, 90, 60], detail={"cell_bbox": [60, 50, 90, 60], "note": "caller"})
    elif case == "uncertified":
        for region in regions:
            region.pop("table_topology")
    elif case == "missing_cells":
        for region in regions:
            region.pop("cells")
    elif case == "malformed":
        regions = [{"id": "pressure", "kind": "table", "cells": "not cells", "table_topology": {}}]
    elif case == "ambiguous_topology":
        for region in regions:
            region["table_topology"]["status"] = "ambiguous"
    elif case == "no_scope":
        data["rows"][0].pop("source_ref")
    elif case == "unknown_origin":
        ref["coord_origin"] = None
    elif case == "new_origin":
        ref.pop("coord_origin")
    if case != "empty_store":
        asyncio.run(ops.runtime.doc_store.write_gold_region_file("doc", 1, regions[::-1] if reverse else regions))
    expected = deepcopy(data)
    if case in {"inferred", "new_origin"}:
        expected["rows"][0]["source_ref"].update(
            bbox=[60, 50, 90, 60], region_id="pressure", coord_origin="top-left",
        )
    node_id = ops.call("add", data)
    assert ops.read(node_id) == expected
    ops.call("update", data, node_id)
    assert ops.read(node_id) == expected
    # Sending the persisted, resolved data back is idempotent too.
    ops.call("update", expected, node_id)
    assert ops.read(node_id) == expected


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_row_creation_uses_existing_defaults_and_preserves_patch_deletions(transport, tmp_path):
    ops = CanvasOperations(transport, AnchorConfig(data_dir=tmp_path))
    asyncio.run(ops.runtime.workspace.create_workspace("g6"))
    asyncio.run(ops.runtime.doc_store.write_gold_region_file("doc", 1, _regions()))
    data = _input("exact")
    data["source_ref"] = data["rows"][0].pop("source_ref")
    created = ops.read(ops.call("add", data))
    node_id = ops.call("add", {"source_ref": data["source_ref"], "description": "remove", "rows": []})
    ops.call("update", {"rows": data["rows"], "description": None}, node_id)
    assert ops.read(node_id) == created


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_create_and_update_use_current_generation_gold(transport, tmp_path):
    ops = CanvasOperations(transport, AnchorConfig(data_dir=tmp_path))
    store = ops.runtime.doc_store

    async def replace():
        await ops.runtime.workspace.create_workspace("g6")
        await pipeline(store, [["OLD"]]).ingest_pdf(b"A", "doc.pdf")
        await store.write_gold_region_file("doc", 1, _regions())
        old = store.snapshot("doc")
        await pipeline(store, [["NEW"]]).ingest_pdf(b"B", "doc.pdf", force=True)
        await store.write_gold_region_file("doc", 1, canonical_regions([{
            "id": "pressure", "page": 1, "kind": "table", "bbox": [0, 0, 100, 100],
            "cells": [{"row": 0, "col": 0, "text": "Pressure", "bbox": [10, 70, 55, 80]},
                      {"row": 0, "col": 1, "text": "43", "bbox": [60, 70, 90, 80]}],
        }], origin="top-left"))
        assert (await old.get_regions("doc", 1))["pages"][1][1]["cells"][1]["text"] == "42"
        assert (await store.get_raw_pdf_path("doc")).read_bytes() == b"B"

    asyncio.run(replace())
    for value in ("42", "43"):
        data = _input("exact")
        data["rows"][0]["value"] = value
        expected = deepcopy(data)
        if value == "43":
            expected["rows"][0]["source_ref"]["bbox"] = [60, 70, 90, 80]
        node_id = ops.call("add", data)
        assert ops.read(node_id) == expected
        ops.call("update", data, node_id)
        assert ops.read(node_id) == expected
