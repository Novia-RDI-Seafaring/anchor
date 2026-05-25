"""HTTP adapter — POST /api/workspaces/{slug}/snapshot.

Uses a fake SnapshotPort to avoid spinning chromium. Asserts:
- 200 + image/png when wired and bytes returned.
- 200 + image/png when wired and a file path is returned.
- 501 when no snapshotter is wired (sensible signal for the agent).
- 400 on unsupported format.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from tests.fixtures.fakes import TINY_PNG_BYTES, FakeSnapshotter
from tests.fixtures.services import make_in_memory_services


def _client_with_snapshotter(snap):
    s = make_in_memory_services()
    s.workspace.snapshotter = snap
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    )
    return TestClient(app), s


def test_snapshot_returns_inline_png_bytes():
    snap = FakeSnapshotter(mode="bytes")
    client, s = _client_with_snapshotter(snap)
    import asyncio
    asyncio.run(s.workspace.create_workspace("w1"))
    rsp = client.post("/api/workspaces/w1/snapshot", json={"format": "png"})
    assert rsp.status_code == 200
    assert rsp.headers["content-type"].startswith("image/png")
    assert rsp.content == TINY_PNG_BYTES


def test_snapshot_returns_file_path_response(tmp_path: Path):
    snap = FakeSnapshotter(mode="path", out_dir=tmp_path)
    client, s = _client_with_snapshotter(snap)
    import asyncio
    asyncio.run(s.workspace.create_workspace("w1"))
    rsp = client.post("/api/workspaces/w1/snapshot", json={"format": "png"})
    assert rsp.status_code == 200
    assert rsp.headers["content-type"].startswith("image/png")
    # FileResponse streams the on-disk bytes; the fake wrote TINY_PNG_BYTES.
    assert rsp.content == TINY_PNG_BYTES


def test_snapshot_without_body_uses_defaults():
    snap = FakeSnapshotter()
    client, s = _client_with_snapshotter(snap)
    import asyncio
    asyncio.run(s.workspace.create_workspace("w1"))
    rsp = client.post("/api/workspaces/w1/snapshot")
    assert rsp.status_code == 200
    assert snap.calls[0]["format"] == "png"
    assert snap.calls[0]["full_page"] is True


def test_snapshot_returns_501_when_no_snapshotter_wired():
    s = make_in_memory_services()  # default has no snapshotter
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    )
    client = TestClient(app)
    import asyncio
    asyncio.run(s.workspace.create_workspace("w1"))
    rsp = client.post("/api/workspaces/w1/snapshot")
    assert rsp.status_code == 501
    assert "no snapshotter" in rsp.json()["detail"]


def test_snapshot_returns_400_for_unknown_format():
    snap = FakeSnapshotter()
    client, s = _client_with_snapshotter(snap)
    import asyncio
    asyncio.run(s.workspace.create_workspace("w1"))
    rsp = client.post("/api/workspaces/w1/snapshot", json={"format": "webp"})
    assert rsp.status_code == 400
