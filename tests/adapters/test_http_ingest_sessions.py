"""HTTP harness ingest-session routes - parity with MCP/CLI."""
from __future__ import annotations

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from tests.fixtures.services import make_in_memory_services


def _client(*, with_sessions: bool = True):
    s = make_in_memory_services(page_count=1)
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
        ingest_session_service=s.ingest_session if with_sessions else None,
    )
    return TestClient(app), s


def test_full_session_loop_over_http(tmp_path):
    client, _s = _client()
    pdf = tmp_path / "demo.pdf"
    pdf.write_bytes(b"%PDF-fake")

    rsp = client.post("/api/ingest/sessions", json={"pdf_path": str(pdf)})
    assert rsp.status_code == 201, rsp.text
    order = rsp.json()
    sid = order["session_id"]
    assert order["page_count"] == 1

    item = client.get(f"/api/ingest/sessions/{sid}/pages/1").json()
    assert item["raw_md"].startswith("# Demo Doc")
    assert item["candidates"]

    verdict = client.put(f"/api/ingest/sessions/{sid}/pages/1", json={
        "regions": [{"kind": "text", "title": "Intro", "member_item_ids": ["p1-i0"]}],
        "polished_md": "# polished",
    }).json()
    assert verdict["accepted"] is True

    by_slug = client.get("/api/ingest/sessions", params={"slug": "demo"}).json()
    assert by_slug["session_id"] == sid
    assert by_slug["pages_remaining"] == []

    summary = client.post(f"/api/ingest/sessions/{sid}/finalize", json={
        "declared_model": "claude-fable-5",
    }).json()
    assert summary["finalized"] is True
    assert summary["declared_model"] == "claude-fable-5"

    docs = client.get("/api/documents").json()
    assert isinstance(docs, list)


def test_rejected_submission_returns_verdict_not_5xx(tmp_path):
    client, _s = _client()
    pdf = tmp_path / "demo.pdf"
    pdf.write_bytes(b"%PDF-fake")
    sid = client.post("/api/ingest/sessions", json={"pdf_path": str(pdf)}).json()["session_id"]
    rsp = client.put(f"/api/ingest/sessions/{sid}/pages/1", json={
        "regions": [{"kind": "text", "title": "no geometry"}],
    })
    assert rsp.status_code == 200
    body = rsp.json()
    assert body["accepted"] is False
    assert body["errors"]


def test_unknown_session_is_404_and_abort_works(tmp_path):
    client, _s = _client()
    assert client.get("/api/ingest/sessions/ing-nope").status_code == 404
    assert client.delete("/api/ingest/sessions/ing-nope").status_code == 404
    pdf = tmp_path / "demo.pdf"
    pdf.write_bytes(b"%PDF-fake")
    sid = client.post("/api/ingest/sessions", json={"pdf_path": str(pdf)}).json()["session_id"]
    rsp = client.delete(f"/api/ingest/sessions/{sid}")
    assert rsp.status_code == 200
    assert rsp.json()["aborted"] is True


def test_missing_pdf_is_404():
    client, _s = _client()
    rsp = client.post("/api/ingest/sessions", json={"pdf_path": "/nope/missing.pdf"})
    assert rsp.status_code == 404


def test_unwired_session_service_is_503():
    client, _s = _client(with_sessions=False)
    rsp = client.get("/api/ingest/sessions", params={"slug": "demo"})
    assert rsp.status_code == 503
