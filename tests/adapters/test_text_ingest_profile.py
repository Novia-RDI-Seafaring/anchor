"""CLI, MCP and HTTP expose the same explicit text ingestion path."""
import asyncio
import json
from types import SimpleNamespace

from typer.testing import CliRunner

from anchor.adapters.cli import documents
from anchor.adapters.cli.main import app
from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
from tests.adapters.test_http_upload_intent import _client
from tests.core.test_text_ingest_profile import pipeline


def test_cli_text_profile_creates_gold_without_a_vision_provider(tmp_path, monkeypatch):
    service, store = pipeline(vision=False)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-fake")
    config = SimpleNamespace(polish_model="unused", region_model="unused", dpi=72)
    monkeypatch.setattr(documents, "_build_real_services", lambda _: (config, None, None, service, store))
    result = CliRunner().invoke(app, ["ingest", str(pdf), "--profile", "text"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["region_count"] == 1
    assert asyncio.run(store.has_gold("doc"))


def test_mcp_text_profile_creates_gold_without_a_skip_note(tmp_path):
    service, store = pipeline(vision=False)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-fake")
    result = json.loads(asyncio.run(call_tool(service, store, "ingest_pdf", {
        "pdf_path": str(pdf), "profile": "text",
    })))
    assert result["region_count"] == 1
    assert "note" not in result
    assert asyncio.run(store.has_gold("doc"))


def test_http_text_profile_runs_in_harness_project_without_an_intent():
    client, services = _client("harness")
    services.ingest.region_extractor = None
    services.ingest.polisher = None
    with client:
        response = client.post("/api/workspaces/cv/upload", data={"profile": "text"},
                               files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "started"
        assert client.get("/api/intents").json()["count"] == 0
        assert asyncio.run(services.doc_store.has_gold("doc"))


def test_http_unknown_profile_rejects_before_creating_placeholder():
    client, services = _client("harness")
    response = client.post("/api/workspaces/cv/upload", data={"profile": "unknown"},
                           files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")})
    assert response.status_code == 422
    assert asyncio.run(services.workspace.get_state("cv"))["nodes"] == []
