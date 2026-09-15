"""Derive uses the canonical parent through every supported adapter."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from mcp.types import CallToolRequest, CallToolRequestParams
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime
from anchor.extensions.anchor_pdfs.core.region_inspect import inspect_region
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.config import AnchorConfig


def derive_via(transport, config, slug, locator, region, *, success=True):
    if transport == "cli":
        result = CliRunner().invoke(cli_app, ["derive-region", slug, locator,
            "--region", json.dumps(region), "--data-dir", str(config.data_dir)])
        assert (result.exit_code == 0) == success, result.output
        return json.loads(result.stdout) if success else result.output
    runtime = build_project_runtime(config, profile=RuntimeProfile.INGEST)
    if transport == "http":
        app = build_app(workspace_service=runtime.workspace, doc_store=runtime.doc_store,
            bus=runtime.bus, ingest_service=IngestService(runtime.doc_store, runtime.bus,
                extractor=object(), renderer=object()))
        with TestClient(app) as client:
            result = client.post(f"/api/documents/{slug}/derived-regions", json={
                "parent_region_id": locator, "region": region,
            })
        assert (result.status_code == 200) == success, result.text
        return result.json()
    server = build_mcp_server(bundle=runtime)

    async def invoke():
        result = await server.request_handlers[CallToolRequest](CallToolRequest(
            method="tools/call", params=CallToolRequestParams(name="derive_region", arguments={
                "slug": slug, "parent_region_id": locator, "region": region,
            }),
        ))
        return json.loads(result.root.content[0].text)

    result = asyncio.run(invoke())
    assert ("error" not in result) == success, result
    return result


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
def test_derive_and_read_preserve_exact_parent_across_adapters(tmp_path, transport):
    store = FsDocStore(tmp_path)
    for page in (1, 2):
        asyncio.run(store.write_gold_region_file("doc", page, [{
            "id": "r1", "kind": "chart", "bbox": [20, 30, 200, 100],
        }]))
    config = AnchorConfig(data_dir=tmp_path)
    region = {"id": "child", "kind": "chart_series", "title": "Derived chart"}
    derive_via(transport, config, "doc", "r1", region, success=False)
    derive_via(transport, config, "doc", "p2/r1", {**region, "page": 3}, success=False)
    out = derive_via(transport, config, "doc", "p2/r1", region)
    assert out["derived_from"] == "p2/r1"
    child = asyncio.run(inspect_region(FsDocStore(tmp_path), "doc", "p2/child"))
    assert child["source_ref"] == {
        "slug": "doc", "page": 2, "region_id": "child",
        "bbox": [20, 30, 200, 100], "coord_origin": "top-left",
    }
    assert child["derived_from"] == "p2/r1"
    assert asyncio.run(inspect_region(store, "doc", "p1/child")) is None
