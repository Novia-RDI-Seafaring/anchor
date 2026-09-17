"""remove-region adapter parity (#304): CLI / HTTP / MCP hit the same core op.

`IngestService.remove_region` deletes one OIP-derived gold region (guarded:
model-extracted gold is refused) and keeps the embedding index consistent.
Every adapter surfaces the same envelope / structured error.
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
from anchor.adapters.mcp import tiering
from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
from tests.fixtures.services import make_in_memory_services

REGIONS = [
    {"id": "r1", "kind": "chart", "title": "Flow chart",
     "bbox": [56.5, 58.5, 252.8, 223.2]},
    {"id": "r2", "kind": "chart_series", "title": "Digitized series",
     "derived_from": "r1",
     "source_ref": {"slug": "lkh", "page": 4, "region_id": "r1",
                    "bbox": [56.5, 58.5, 252.8, 223.2]}},
]


def _seed_memory():
    s = make_in_memory_services()
    asyncio.run(s.doc_store.write_gold_region_file("lkh", 4, [dict(r) for r in REGIONS]))
    return s


# ── MCP ─────────────────────────────────────────────────────────────────────

def test_mcp_remove_region_removes_and_reports():
    s = _seed_memory()
    out = json.loads(asyncio.run(
        call_tool(s.ingest, s.doc_store, "remove_region", {"slug": "lkh", "region_id": "r2"})
    ))
    assert out["removed"] is True and out["region_id"] == "r2"
    regs = asyncio.run(s.doc_store.get_regions("lkh", page=4))["pages"][4]
    assert [r["id"] for r in regs] == ["r1"]


def test_mcp_remove_region_refuses_model_extracted_gold():
    s = _seed_memory()
    out = json.loads(asyncio.run(
        call_tool(s.ingest, s.doc_store, "remove_region", {"slug": "lkh", "region_id": "r1"})
    ))
    assert "model-extracted" in out["error"]


def test_mcp_remove_region_listed_in_document_advanced_capability():
    group = next(
        g for g in tiering._CAPABILITY_GROUPS if g["capability"] == "document_advanced"
    )
    assert "remove_region" in group["names"]


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


def test_http_delete_region_removes_derived():
    client, s = _client()
    rsp = client.delete("/api/documents/lkh/regions/p4/r2")
    assert rsp.status_code == 200
    body = rsp.json()
    assert body["removed"] is True and body["region_id"] == "r2"
    regs = asyncio.run(s.doc_store.get_regions("lkh", page=4))["pages"][4]
    assert [r["id"] for r in regs] == ["r1"]


def test_http_delete_region_refuses_gold_with_409():
    client, _ = _client()
    rsp = client.delete("/api/documents/lkh/regions/r1")
    assert rsp.status_code == 409
    assert "model-extracted" in rsp.json()["detail"]


def test_http_delete_region_unknown_is_404():
    client, _ = _client()
    rsp = client.delete("/api/documents/lkh/regions/r9")
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
        await doc_store.write_gold_region_file("lkh", 4, [dict(r) for r in REGIONS])
        await doc_store.write_embeddings("lkh", {
            "embed_model": "fake", "dim": 2,
            "vectors": [
                {"page": 4, "region_id": "r1", "text": "chart", "vector": [0.1, 0.2]},
                {"page": 4, "region_id": "r2", "text": "series", "vector": [0.3, 0.4]},
            ],
        })

    asyncio.run(run())


def test_cli_remove_region_removes_and_drops_vector(data_dir):
    _seed_fs(data_dir)
    result = CliRunner().invoke(
        cli_app, ["remove-region", "lkh", "r2", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["removed"] is True
    assert out["embeddings_removed"] == 1

    _, _, _, _, doc_store = _build_real_services(data_dir)
    regs = asyncio.run(doc_store.get_regions("lkh", page=4))["pages"][4]
    assert [r["id"] for r in regs] == ["r1"]
    payload = asyncio.run(doc_store.get_embeddings("lkh"))
    assert [v["region_id"] for v in payload["vectors"]] == ["r1"]


def test_cli_remove_region_refuses_gold_with_one_liner(data_dir):
    _seed_fs(data_dir)
    result = CliRunner().invoke(
        cli_app, ["remove-region", "lkh", "r1", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 1
    assert "model-extracted" in result.output
    assert "Traceback" not in result.output
