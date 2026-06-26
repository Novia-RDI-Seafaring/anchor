"""Adapter parity for locate_text (anchor#197, slice 2 of #145).

The same value-locator must round-trip through MCP (`locate_text`), CLI
(`anchor locate-text`), and HTTP (`GET /api/documents/{slug}/pages/{page}/
locate`), each returning `{slug, page, query, quads}` with a plausible
non-empty quad for a known value and an empty list for a nonsense query.
locate_text reads the bronze PDF, so each adapter is exercised against a real
FsDocStore with a stashed one-page PDF and the real PymupdfPdfRenderer.
"""
from __future__ import annotations

import asyncio
import json

import pymupdf
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.adapters.mcp import tiering
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs import mcp_handlers
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore

PAGE_W = 595.3
PAGE_H = 841.9
KNOWN = "LKH-5"


def _pdf_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text((100, 100), KNOWN, fontsize=12)
    out = doc.tobytes()
    doc.close()
    return out


async def _seed(store: FsDocStore) -> None:
    # Stash the bronze PDF and the silver index so get_raw_pdf_path (which
    # recovers the bronze filename from the index) can resolve the document.
    await store.stash_bronze(_pdf_bytes(), "lkh.pdf")
    await store.write_silver_artifact(
        "lkh", "index.json",
        json.dumps({
            "document": {"title": "LKH", "filename": "lkh.pdf", "page_count": 1},
            "outline": [],
        }),
    )


def _ingest(store: FsDocStore, bus: MemoryEventBus) -> IngestService:
    return IngestService(store, bus, extractor=object(), renderer=PymupdfPdfRenderer())


def _assert_hit(out: dict) -> None:
    assert out["slug"] == "lkh"
    assert out["page"] == 1
    assert out["query"] == KNOWN
    assert out["quads"], "expected a non-empty quad for a known value"
    left, yb0, right, yb1 = out["quads"][0]
    assert right > left and yb1 >= yb0


# ── MCP ─────────────────────────────────────────────────────────────────────


def test_mcp_locate_text_round_trips(tmp_path):
    store = FsDocStore(tmp_path)
    asyncio.run(_seed(store))
    ingest = _ingest(store, MemoryEventBus())

    raw = asyncio.run(mcp_handlers.call_tool(
        ingest, store, "locate_text", {"slug": "lkh", "page": 1, "query": KNOWN},
    ))
    _assert_hit(json.loads(raw))


def test_mcp_locate_text_nonsense_is_empty(tmp_path):
    store = FsDocStore(tmp_path)
    asyncio.run(_seed(store))
    ingest = _ingest(store, MemoryEventBus())

    raw = asyncio.run(mcp_handlers.call_tool(
        ingest, store, "locate_text", {"slug": "lkh", "page": 1, "query": "zzz-nope"},
    ))
    assert json.loads(raw)["quads"] == []


def test_mcp_locate_text_is_advertised_and_dispatchable():
    assert "locate_text" in tiering.CORE_PDF_NAMES
    assert "locate_text" in tiering.CORE_NAMES
    assert any(d["name"] == "locate_text" for d in mcp_handlers.tool_definitions())


# ── HTTP ─────────────────────────────────────────────────────────────────────


def _http_app(tmp_path):
    store = FsDocStore(tmp_path)
    asyncio.run(_seed(store))
    bus = MemoryEventBus()
    workspace = WorkspaceService(MemoryWorkspaceStore(), bus)
    ingest = _ingest(store, bus)
    return build_app(
        workspace_service=workspace, ingest_service=ingest, doc_store=store, bus=bus,
    )


def test_http_locate_text_round_trips(tmp_path):
    resp = TestClient(_http_app(tmp_path)).get(
        "/api/documents/lkh/pages/1/locate", params={"query": KNOWN},
    )
    assert resp.status_code == 200, resp.text
    _assert_hit(resp.json())


def test_http_locate_text_nonsense_is_empty(tmp_path):
    resp = TestClient(_http_app(tmp_path)).get(
        "/api/documents/lkh/pages/1/locate", params={"query": "zzz-nope"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quads"] == []


def test_http_locate_text_unknown_slug_404(tmp_path):
    resp = TestClient(_http_app(tmp_path)).get(
        "/api/documents/nope/pages/1/locate", params={"query": KNOWN},
    )
    assert resp.status_code == 404


def test_http_locate_text_bad_bbox_400(tmp_path):
    resp = TestClient(_http_app(tmp_path)).get(
        "/api/documents/lkh/pages/1/locate", params={"query": KNOWN, "bbox": "1,2,3"},
    )
    assert resp.status_code == 400


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_locate_text_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    data_dir = tmp_path / "data"

    from anchor.adapters.cli.services import _build_real_services

    _, _, _, _, doc_store = _build_real_services(data_dir)
    asyncio.run(_seed(doc_store))

    result = CliRunner().invoke(
        cli_app,
        ["locate-text", "lkh", "1", KNOWN, "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 0, result.output
    _assert_hit(json.loads(result.output))


def test_cli_locate_text_nonsense_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    data_dir = tmp_path / "data"

    from anchor.adapters.cli.services import _build_real_services

    _, _, _, _, doc_store = _build_real_services(data_dir)
    asyncio.run(_seed(doc_store))

    result = CliRunner().invoke(
        cli_app,
        ["locate-text", "lkh", "1", "zzz-nope", "--data-dir", str(data_dir)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["quads"] == []
