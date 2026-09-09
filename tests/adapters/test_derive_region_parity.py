"""derive-region parent-token parity (#287): CLI / HTTP / MCP hit the same op.

Region ids are only unique per page, so `IngestService.derive_region` accepts
the `p<page>/r<n>` token `inspect_region` uses and refuses a bare id that
matches regions on multiple pages with a structured error listing the
candidate pages. Every adapter surfaces the same behavior.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.cli.services import _build_real_services
from anchor.adapters.http.app import build_app
from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
from tests.fixtures.services import make_in_memory_services

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
    assert out["derived_from"] == "r1"
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
    assert rsp.json()["derived_from"] == "r1"


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
    assert json.loads(result.output)["derived_from"] == "r1"


def test_cli_derive_region_bare_ambiguous_fails_with_one_liner(data_dir):
    _seed_fs(data_dir)
    result = CliRunner().invoke(cli_app, [
        "derive-region", "lkh", "r1",
        "--region", json.dumps(SERIES), "--data-dir", str(data_dir),
    ])
    assert result.exit_code == 1
    assert "p1/r1" in result.output
    assert "Traceback" not in result.output
