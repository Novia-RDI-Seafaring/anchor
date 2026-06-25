"""Adapter parity for pointed extraction (anchor#132).

The same selected-regions -> caller-shape extraction must round-trip through
MCP (`extract_pointed`), CLI (`anchor extract`), and HTTP
(`POST /api/documents/{slug}/extract`), each returning `{doc_slug, data,
provenance, unfilled}` with a provenance entry per filled leaf. No model is
called.
"""
from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp import tiering
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs import mcp_handlers
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore

_SHAPE = {"model": "string", "max_inlet_pressure": "quantity"}


async def _seed(store) -> None:
    await store.write_silver_artifact(
        "lkh", "index.json",
        json.dumps({
            "document": {"title": "LKH", "filename": "lkh.pdf", "page_count": 2},
            "outline": [],
        }),
    )
    await store.write_gold_region_file("lkh", 2, [{
        "id": "r4", "kind": "table", "title": "Spec", "page": 2,
        "bbox": [50, 480, 550, 410],
        "cells": [
            {"row": 0, "col": 0, "text": "Model", "bbox": [55, 477, 200, 460]},
            {"row": 0, "col": 1, "text": "LKH-5", "bbox": [210, 477, 360, 460]},
            {"row": 1, "col": 0, "text": "Max inlet pressure", "bbox": [55, 455, 200, 438]},
            {"row": 1, "col": 1, "text": "600 kPa", "bbox": [210, 455, 360, 438]},
        ],
    }])
    await store.mark_gold_complete("lkh", {"mode": "keyed"})


def _assert_envelope(out: dict) -> None:
    assert out["doc_slug"] == "lkh"
    assert out["data"] == {"model": "LKH-5", "max_inlet_pressure": "600 kPa"}
    assert out["provenance"]["/model"]["quote"] == "LKH-5"
    assert out["provenance"]["/max_inlet_pressure"]["bbox"] == [210.0, 455.0, 360.0, 438.0]
    assert out["unfilled"] == []


# ── MCP ─────────────────────────────────────────────────────────────────────


async def test_mcp_extract_pointed_round_trips():
    store = MemoryDocStore()
    await _seed(store)
    ingest = IngestService(store, MemoryEventBus(), extractor=object(), renderer=object())

    raw = await mcp_handlers.call_tool(
        ingest, store, "extract_pointed",
        {"slug": "lkh", "select": {"regions": ["p2/r4"]}, "shape": _SHAPE},
    )
    _assert_envelope(json.loads(raw))


def test_mcp_extract_pointed_is_advertised_and_dispatchable():
    # Primary agent op -> in the always-on core surface (advertised), and the
    # tool definition exists for dispatch.
    assert "extract_pointed" in tiering.CORE_PDF_NAMES
    assert "extract_pointed" in tiering.CORE_NAMES
    assert any(d["name"] == "extract_pointed" for d in mcp_handlers.tool_definitions())


# ── HTTP ─────────────────────────────────────────────────────────────────────


def test_http_extract_pointed_round_trips(tmp_path):
    store = FsDocStore(tmp_path)
    asyncio.run(_seed(store))
    bus = MemoryEventBus()
    workspace = WorkspaceService(MemoryWorkspaceStore(), bus)
    ingest = IngestService(store, bus, extractor=object(), renderer=object())
    app = build_app(
        workspace_service=workspace, ingest_service=ingest, doc_store=store, bus=bus,
    )
    resp = TestClient(app).post(
        "/api/documents/lkh/extract",
        json={"select": {"regions": ["p2/r4"]}, "shape": _SHAPE},
    )
    assert resp.status_code == 200, resp.text
    _assert_envelope(resp.json())


def test_http_extract_pointed_unknown_slug_404(tmp_path):
    store = FsDocStore(tmp_path)
    bus = MemoryEventBus()
    workspace = WorkspaceService(MemoryWorkspaceStore(), bus)
    ingest = IngestService(store, bus, extractor=object(), renderer=object())
    app = build_app(
        workspace_service=workspace, ingest_service=ingest, doc_store=store, bus=bus,
    )
    resp = TestClient(app).post(
        "/api/documents/nope/extract", json={"shape": _SHAPE},
    )
    assert resp.status_code == 404


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_extract_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    data_dir = tmp_path / "data"

    # Seed gold via the same store the CLI command will read from.
    from anchor.adapters.cli.services import _build_real_services

    _, _, _, _, doc_store = _build_real_services(data_dir)
    asyncio.run(_seed(doc_store))

    shape_path = tmp_path / "shape.json"
    shape_path.write_text(json.dumps(_SHAPE), encoding="utf-8")
    out_path = tmp_path / "out.json"

    result = CliRunner().invoke(
        cli_app,
        [
            "extract", "lkh",
            "--shape", str(shape_path),
            "--region", "p2/r4",
            "--output", str(out_path),
            "--data-dir", str(data_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    _assert_envelope(json.loads(out_path.read_text(encoding="utf-8")))
