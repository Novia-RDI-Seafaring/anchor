"""Removed replacement members are unavailable on the public adapters."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pymupdf
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.extensions.anchor_pdfs import mcp_handlers
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline
from tests.fixtures.services import make_in_memory_services


def test_shrinking_replacement_hides_removed_evidence_on_all_adapters(tmp_path, monkeypatch):
    store = FsDocStore(tmp_path)
    originals = []
    for texts in (["CURRENT PAGE", "REMOVE ME"], ["REPLACEMENT PAGE"]):
        with pymupdf.open() as pdf:
            for text in texts:
                pdf.new_page().insert_text((72, 90), text)
            originals.append(pdf.tobytes())
        svc = pipeline(store, [[t] for t in texts])
        svc.renderer = PymupdfPdfRenderer()
        asyncio.run(svc.ingest_pdf(originals[-1], "shared.pdf", slug="doc", force=True))

    reader = FsDocStore(tmp_path)
    services = make_in_memory_services()
    app = build_app(workspace_service=services.workspace, ingest_service=svc,
                    doc_store=reader, bus=services.bus)
    with TestClient(app) as client:
        assert hashlib.sha256(client.get("/api/documents/doc/pdf").content).digest() == hashlib.sha256(originals[1]).digest()
        assert client.get("/api/documents/doc/index").json()["document"]["page_count"] == 1
        for suffix in ("pages/2/text", "pages/2/image", "regions/p2/r1", "region-content/p2/r1",
                       "pages/2/locate?query=REMOVE", "pages/2/crop?bbox=0,0,200,200"):
            assert client.get(f"/api/documents/doc/{suffix}").status_code == 404, suffix
        assert client.get("/api/documents/doc/pages/1/locate?query=REPLACEMENT").json()["quads"]
        gold = client.get("/api/documents/doc/gold-map").json()
        assert set(gold["pages"]) == {"1"}
        hits = client.get("/api/documents/_search?q=REMOVE&k=100").json()["hits"]
        assert hits and all(h["page"] == 1 and "REMOVE" not in h["text"] for h in hits)

    for tool, args in (("inspect_region", {"region_id": "p2/r1"}),
                       ("get_region_content", {"region_id": "p2/r1"}),
                       ("get_page_text", {"page": 2}),
                       ("locate_text", {"page": 2, "query": "REMOVE"})):
        out = asyncio.run(mcp_handlers.call_tool(svc, reader, tool, {"slug": "doc", **args}))
        assert "error" in json.loads(out), (tool, out)

    import anchor.adapters.cli.documents as commands

    monkeypatch.setattr(commands, "_build_real_services", lambda _: (None, None, None, svc, reader))
    for command, args in (("inspect-region", ["p2/r1"]), ("region-content", ["p2/r1"]),
                          ("locate-text", ["2", "REMOVE"])):
        out = CliRunner().invoke(cli_app, [command, "doc", *args])
        assert out.exit_code == 1, out.output
        assert "not found" in out.output or "not available" in out.output, out.output
