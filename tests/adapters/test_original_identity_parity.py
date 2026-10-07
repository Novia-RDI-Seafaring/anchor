"""Real PDF source identity through existing HTTP, MCP and CLI operations."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.extensions.anchor_pdfs import mcp_handlers
from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore
from tests.extensions.anchor_pdfs.test_original_identity import ingest_service, pdf_bytes
from tests.fixtures.fakes import FakeEmbedder
from tests.fixtures.services import make_in_memory_services


def test_two_uploads_resolve_own_pdf_crop_inspection_and_search_on_all_adapters(tmp_path, monkeypatch):
    store = FsDocStore(tmp_path)
    svc = ingest_service(store)
    services = make_in_memory_services()
    sessions = IngestSessionService(
        store, FsIngestSessionStore(tmp_path), services.bus,
        extractor=svc.extractor, renderer=svc.renderer, embedder=FakeEmbedder(),
        embed_model_id="test",
    )
    app = build_app(workspace_service=services.workspace, ingest_service=svc,
                    doc_store=store, bus=services.bus, ingest_session_service=sessions)
    inputs = {"doc-a": pdf_bytes("DOCUMENT A"), "doc-b": pdf_bytes("DOCUMENT B")}
    with TestClient(app) as client:
        for slug, raw in inputs.items():
            response = client.post("/api/ingest/sessions", data={"slug": slug},
                                   files={"file": ("shared.pdf", raw, "application/pdf")})
            assert response.status_code == 201, response.text
            sid = response.json()["session_id"]
            verdict = client.put(f"/api/ingest/sessions/{sid}/pages/1", json={"regions": [{
                "id": "identity", "kind": "text", "title": slug,
                "member_item_ids": ["p1-i0"],
            }]}).json()
            assert verdict["accepted"]
            assert client.post(f"/api/ingest/sessions/{sid}/finalize").status_code == 200

        # Fresh filesystem reader, no cached mapping from the writer.
        app.state.doc_store = FsDocStore(tmp_path)
        for slug, raw in inputs.items():
            response = client.get(f"/api/documents/{slug}/pdf")
            assert response.status_code == 200
            assert hashlib.sha256(response.content).digest() == hashlib.sha256(raw).digest()
            assert 'filename="shared.pdf"' in response.headers["content-disposition"]
            inspect = client.get(f"/api/documents/{slug}/regions/p1/identity").json()
            content = client.get(f"/api/documents/{slug}/region-content/p1/identity").json()
            assert inspect["source_ref"]["slug"] == content["source_ref"]["slug"] == slug
            assert inspect["source_ref"]["coord_origin"] == "top-left"
            assert client.get(f"/api/documents/{slug}/gold-map").json()["slug"] == slug
            own_text = f"DOCUMENT {slug[-1].upper()}"
            assert client.get(f"/api/documents/{slug}/pages/1/locate", params={"query": own_text}).json()["quads"]
            other_text = "DOCUMENT B" if slug == "doc-a" else "DOCUMENT A"
            assert not client.get(f"/api/documents/{slug}/pages/1/locate", params={"query": other_text}).json()["quads"]
            original = tmp_path / f"{slug}.pdf"
            original.write_bytes(raw)
            bbox = [60, 60, 260, 110]
            cropped = client.get(f"/api/documents/{slug}/pages/1/crop",
                                 params={"bbox": ",".join(map(str, bbox)), "dpi": 150})
            assert cropped.content == asyncio.run(svc.renderer.crop_region(original, 1, bbox, dpi=150))
            assert client.get(f"/api/documents/{slug}/pages/1/image").content == asyncio.run(
                svc.renderer.render_pages(original, dpi=150)
            )[1]

    reader = FsDocStore(tmp_path)
    for slug, raw in inputs.items():
        payload = json.loads(asyncio.run(mcp_handlers.call_tool(
            svc, reader, "get_pdf", {"slug": slug, "format": "base64"},
        )))
        assert base64.b64decode(payload["value"]) == raw
        # Swap only runtime assembly; execute the actual CLI command/read path.
        import anchor.adapters.cli.documents as commands
        monkeypatch.setattr(commands, "_build_real_services", lambda _: (None, None, None, None, reader))
        output = tmp_path / f"{slug}-cli.pdf"
        result = CliRunner().invoke(cli_app, ["pdf", slug, "--copy-to", str(output)])
        assert result.exit_code == 0, result.output
        assert output.read_bytes() == raw

    # Search joins preserve slug even when equal scores and text occur.
    search_svc = IngestService(reader, services.bus, extractor=svc.extractor,
                               renderer=svc.renderer, embedder=FakeEmbedder(), embed_model_id="test")
    hits = asyncio.run(search_svc.search("identity"))["hits"]
    assert {h["slug"] for h in hits} == set(inputs)
    for hit in hits:
        assert asyncio.run(reader.get_raw_pdf_path(hit["slug"])).read_bytes() == inputs[hit["slug"]]


def test_rejected_forced_session_preserves_session_and_cli_reports_conflict(tmp_path, monkeypatch):
    store = FsDocStore(tmp_path)
    svc = ingest_service(store)
    services = make_in_memory_services()
    sessions = IngestSessionService(store, FsIngestSessionStore(tmp_path), services.bus,
                                    extractor=svc.extractor, renderer=svc.renderer)
    raw = pdf_bytes("DOCUMENT A")
    order = asyncio.run(sessions.ingest_begin(raw, "shared.pdf", slug="doc-a"))
    receipt = store.bronze / "doc-a" / "original.json"
    record = json.loads(receipt.read_text(encoding="utf-8"))
    record["slug"] = "other"
    receipt.write_text(json.dumps(record), encoding="utf-8")
    app = build_app(workspace_service=services.workspace, ingest_service=svc,
                    doc_store=store, bus=services.bus, ingest_session_service=sessions)
    with TestClient(app) as client:
        response = client.post("/api/ingest/sessions", data={"slug": "doc-a", "force": "true"},
                               files={"file": ("shared.pdf", pdf_bytes("DOCUMENT B"), "application/pdf")})
        assert response.status_code == 400
        assert str(tmp_path) not in response.text
    assert asyncio.run(sessions.ingest_status(order["session_id"]))["state"] == "open"
    assert (asyncio.run(store.get_raw_pdf_path("doc-a"))).read_bytes() == raw

    import anchor.adapters.cli.ingest_session as commands
    monkeypatch.setattr(commands, "_build_session_services", lambda _: (None, sessions))
    original = tmp_path / "shared.pdf"
    original.write_bytes(raw)
    result = CliRunner().invoke(cli_app, ["ingest-session", "begin", str(original), "--slug", "doc-a", "--force"])
    assert result.exit_code == 1
    assert '"error"' in result.output
    assert str(tmp_path) not in result.output
