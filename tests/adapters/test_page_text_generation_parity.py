"""Same-page replacement agrees across text, inspect, source and search readers."""
import asyncio
import hashlib
import json
from types import SimpleNamespace

import pymupdf
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.extensions.anchor_pdfs import mcp_handlers
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from tests.extensions.anchor_pdfs.test_page_text_generations import Polisher
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline
from tests.fixtures.services import make_in_memory_services


def test_same_page_replacement_text_inspect_search_and_original_agree(tmp_path, monkeypatch):
    import anchor.adapters.cli.documents as commands

    store = FsDocStore(tmp_path)
    for token in ("OLD_GENERATION_TEXT", "NEW_GENERATION_TEXT"):
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 90), token)
            original = pdf.tobytes()
        svc = pipeline(store, [[token]])
        svc.renderer = PymupdfPdfRenderer()
        svc.polisher = Polisher()
        if token.startswith("OLD"):
            asyncio.run(svc.ingest_pdf(original, "doc.pdf", slug="doc"))
        else:
            source_file = tmp_path / "doc.pdf"
            source_file.write_bytes(original)
            config = SimpleNamespace(polish_model="test", region_model="test", dpi=72)
            monkeypatch.setattr(commands, "_build_real_services", lambda _, cfg=config, ingester=svc: (cfg, None, None, ingester, store))
            result = CliRunner().invoke(cli_app, ["ingest", str(source_file), "--force", "--skip-polish"])
            assert result.exit_code == 0, result.output
    reader = FsDocStore(tmp_path)
    services = make_in_memory_services()
    app = build_app(workspace_service=services.workspace, ingest_service=svc, doc_store=reader, bus=services.bus)
    with TestClient(app) as client:
        for suffix in ("pages/1/text", "regions/p1/r1", "region-content/p1/r1", "gold-map"):
            response = client.get(f"/api/documents/doc/{suffix}")
            assert response.status_code == 200, response.text
            assert "NEW_GENERATION_TEXT" in response.text and "OLD_GENERATION_TEXT" not in response.text
        assert hashlib.sha256(client.get("/api/documents/doc/pdf").content).digest() == hashlib.sha256(original).digest()
        assert client.get("/api/documents/doc/pages/1/locate?query=NEW_GENERATION_TEXT").json()["quads"]
        assert not client.get("/api/documents/doc/pages/1/locate?query=OLD_GENERATION_TEXT").json()["quads"]
        hits = client.get("/api/documents/_search?q=OLD_GENERATION_TEXT&k=100").json()["hits"]
        assert hits and all("NEW_GENERATION_TEXT" in h["text"] and "OLD_GENERATION_TEXT" not in h["text"] for h in hits)
    for tool, args in (("get_page_text", {"page": 1}), ("inspect_region", {"region_id": "p1/r1"}),
                       ("get_region_content", {"region_id": "p1/r1"})):
        out = asyncio.run(mcp_handlers.call_tool(svc, reader, tool, {"slug": "doc", **args}))
        if tool != "get_page_text":
            assert "error" not in json.loads(out)
        assert "NEW_GENERATION_TEXT" in out and "OLD_GENERATION_TEXT" not in out
    monkeypatch.setattr(commands, "_build_real_services", lambda _: (None, None, None, svc, reader))
    for command, args in (("page-text", ["1"]), ("inspect-region", ["p1/r1"]), ("region-content", ["p1/r1"])):
        out = CliRunner().invoke(cli_app, [command, "doc", *args])
        assert out.exit_code == 0, out.output
        assert "NEW_GENERATION_TEXT" in out.output and "OLD_GENERATION_TEXT" not in out.output
