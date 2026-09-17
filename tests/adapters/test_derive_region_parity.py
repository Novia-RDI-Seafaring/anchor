"""Derive uses the canonical parent through every supported adapter."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from mcp.types import CallToolRequest, CallToolRequestParams
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.cli.services import _build_real_services
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime
from anchor.extensions.anchor_pdfs.core.region_inspect import inspect_region
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
from anchor.infra.config import AnchorConfig
from tests.fixtures.services import make_in_memory_services


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



PAGE1 = [{"id": "r1", "kind": "logo", "title": "Logo", "bbox": [10.0, 10.0, 60.0, 30.0]}]
PAGE4 = [{"id": "r1", "kind": "chart", "title": "Flow chart", "bbox": [56.5, 58.5, 252.8, 223.2]}]
SERIES = {"id": "series-1", "kind": "chart_series", "title": "Digitized series"}


def _seed_memory():
    s = make_in_memory_services()

    async def run():
        await s.doc_store.write_gold_region_file("lkh", 1, [dict(r) for r in PAGE1])
        await s.doc_store.write_gold_region_file("lkh", 4, [dict(r) for r in PAGE4])

    asyncio.run(run())
    return s


# ── MCP ─────────────────────────────────────────────────────────────────────

def test_mcp_derive_region_accepts_page_qualified_parent():
    s = _seed_memory()
    out = json.loads(asyncio.run(call_tool(
        s.ingest, s.doc_store, "derive_region",
        {"slug": "lkh", "parent_region_id": "p4/r1", "region": dict(SERIES)},
    )))
    assert out["derived_from"] == "p4/r1"
    regs = asyncio.run(s.doc_store.get_regions("lkh", page=4))["pages"][4]
    series = next(r for r in regs if r["kind"] == "chart_series")
    assert series["source_ref"]["page"] == 4


def test_mcp_derive_region_bare_ambiguous_reports_candidate_pages():
    s = _seed_memory()
    out = json.loads(asyncio.run(call_tool(
        s.ingest, s.doc_store, "derive_region",
        {"slug": "lkh", "parent_region_id": "r1", "region": dict(SERIES)},
    )))
    assert "pages" in out["error"]
    assert out["candidate_pages"] == [1, 4]


# ── HTTP ────────────────────────────────────────────────────────────────────

def _client():
    s = _seed_memory()
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    )
    return TestClient(app), s


def test_http_derive_region_accepts_page_qualified_parent():
    client, s = _client()
    rsp = client.post(
        "/api/documents/lkh/derived-regions",
        json={"parent_region_id": "p4/r1", "region": dict(SERIES)},
    )
    assert rsp.status_code == 200
    assert rsp.json()["derived_from"] == "p4/r1"


def test_http_derive_region_bare_ambiguous_is_409_with_pages():
    client, _ = _client()
    rsp = client.post(
        "/api/documents/lkh/derived-regions",
        json={"parent_region_id": "r1", "region": dict(SERIES)},
    )
    assert rsp.status_code == 409
    detail = rsp.json()["detail"]
    assert detail["candidate_pages"] == [1, 4]
    assert "p1/r1" in detail["error"]


def test_http_derive_region_unknown_parent_stays_404():
    client, _ = _client()
    rsp = client.post(
        "/api/documents/lkh/derived-regions",
        json={"parent_region_id": "r9", "region": dict(SERIES)},
    )
    assert rsp.status_code == 404


# ── CLI ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Isolated data dir with HOME-isolation so no real anchor.toml is picked up."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    return tmp_path / "data"


def _seed_fs(data_dir) -> None:
    _, _, _, _, doc_store = _build_real_services(data_dir)

    async def run():
        await doc_store.write_gold_region_file("lkh", 1, [dict(r) for r in PAGE1])
        await doc_store.write_gold_region_file("lkh", 4, [dict(r) for r in PAGE4])

    asyncio.run(run())


def test_cli_derive_region_accepts_page_qualified_parent(data_dir):
    _seed_fs(data_dir)
    result = CliRunner().invoke(cli_app, [
        "derive-region", "lkh", "p4/r1",
        "--region", json.dumps(SERIES), "--data-dir", str(data_dir),
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["derived_from"] == "p4/r1"


def test_cli_derive_region_bare_ambiguous_fails_with_one_liner(data_dir):
    _seed_fs(data_dir)
    result = CliRunner().invoke(cli_app, [
        "derive-region", "lkh", "r1",
        "--region", json.dumps(SERIES), "--data-dir", str(data_dir),
    ])
    assert result.exit_code == 1
    assert "p1/r1" in result.output
    assert "Traceback" not in result.output
