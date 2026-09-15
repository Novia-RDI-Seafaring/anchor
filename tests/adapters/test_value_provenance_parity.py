"""G2 resolution through the three existing update/enrichment operations."""

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
from tests.fixtures.tables import canonical_regions


def _regions(*, repeated=False):
    result = []
    for name, key, top in [("temperature", "Temperature", 10), ("pressure", "Pressure", 50)]:
        result.append(
            {
                "id": name,
                "page": 1,
                "kind": "table",
                "bbox": [0, top, 100, top + 20],
                "cells": [
                    {
                        "row": 0,
                        "col": 0,
                        "text": "Pressure" if repeated else key,
                        "bbox": [10, top, 55, top + 10],
                    },
                    {"row": 0, "col": 1, "text": "42", "bbox": [60, top, 90, top + 10]},
                ],
            }
        )
    return canonical_regions(result, origin="top-left")


def _input(case):
    ref = {
        "slug": "doc",
        "page": 1,
        "region_id": "pressure",
        "bbox": [0, 0, 100, 100],
        "coord_origin": "top-left",
    }
    row = {"key": "Pressure", "value": "42", "source_ref": ref}
    if case == "missing":
        ref["region_id"], ref["bbox"] = "missing-r9", [200, 200, 250, 230]
    elif case == "wrong_key":
        ref["region_id"] = "temperature"
    elif case == "wrong_value":
        row["value"] = "41"
    elif case == "conflicting_bbox":
        ref["bbox"] = [200, 200, 250, 230]
    elif case in {"inferred", "ambiguous"}:
        ref.pop("region_id")
    elif case == "uncertified":
        pass
    elif case != "exact":
        raise AssertionError(case)
    return {"rows": [row]}


@pytest.mark.parametrize("adapter", ["http", "mcp", "cli"])
@pytest.mark.parametrize("mixed_parent", [False, True])
@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "wrong_key",
        "wrong_value",
        "conflicting_bbox",
        "inferred",
        "ambiguous",
        "uncertified",
        "exact",
    ],
)
def test_existing_update_operations_share_strict_resolution(adapter, mixed_parent, case, tmp_path):
    config = AnchorConfig(data_dir=tmp_path / "data")
    runtime = build_project_runtime(config, profile=RuntimeProfile.CANVAS)

    async def seed():
        await runtime.workspace.create_workspace("g2")
        await runtime.workspace.add_node("g2", id="spec", node_type="spec")
        await runtime.workspace.add_node("g2", id="area", node_type="area")
        regions = _regions(repeated=case == "ambiguous")
        if case == "uncertified":
            for region in regions:
                region.pop("table_topology")
        await runtime.doc_store.write_gold_region_file("doc", 1, regions)

    asyncio.run(seed())
    data = _input(case)
    expected = deepcopy(data)
    if case in {"exact", "inferred"}:
        expected["rows"][0]["source_ref"].update(region_id="pressure", bbox=[60, 50, 90, 60])
    fields = {"data": data}
    if mixed_parent:
        fields["parent"] = "area"

    if adapter == "http":
        app = build_app(
            workspace_service=runtime.workspace,
            doc_store=runtime.doc_store,
            bus=runtime.bus,
            ingest_service=IngestService(
                runtime.doc_store, runtime.bus, extractor=object(), renderer=object()
            ),
        )
        response = TestClient(app).patch("/api/workspaces/g2/nodes/spec", json=fields)
        assert response.status_code == 200, response.text
    elif adapter == "mcp":
        server = build_mcp_server(bundle=runtime)

        async def update():
            result = await server.request_handlers[CallToolRequest](
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="canvas_update_node",
                        arguments={"workspace_slug": "g2", "id": "spec", **fields},
                    ),
                )
            )
            out = json.loads(result.root.content[0].text)
            assert "error" not in out, out

        asyncio.run(update())
    else:
        args = [
            "canvas",
            "update-node",
            "g2",
            "spec",
            "--data",
            json.dumps(data),
            "--data-dir",
            str(config.data_dir),
        ]
        if mixed_parent:
            args += ["--parent", "area"]
        result = CliRunner().invoke(cli_app, args)
        assert result.exit_code == 0, result.output

    # Reopen persistence through a fresh runtime, including CLI's separate process model.
    reopened = build_project_runtime(config, profile=RuntimeProfile.CANVAS)
    state = asyncio.run(reopened.workspace.get_state("g2"))
    spec = next(node for node in state["nodes"] if node["id"] == "spec")
    actual = deepcopy(spec["data"])
    evidence = actual["rows"][0].pop("evidence", {})
    assert actual == expected
    assert (evidence.get("status") == "verified") == (case in {"exact", "inferred"})
    assert spec.get("parent") == ("area" if mixed_parent else None)
