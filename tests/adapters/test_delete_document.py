"""Deleting a document: refused while cited unless forced, same on every surface."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from anchor.adapters.document_delete import delete_document, find_citations
from anchor.adapters.http.app import build_app
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from tests.extensions.anchor_pdfs.test_replacement_generations import pipeline
from tests.fixtures.services import make_in_memory_services


@pytest.mark.parametrize("memory", [False, True])
def test_the_store_removes_everything_for_the_document(tmp_path, memory):
    async def run():
        store = MemoryDocStore() if memory else FsDocStore(tmp_path)
        await pipeline(store, [["PAGE ONE"]]).ingest_pdf(b"%PDF a", "a.pdf", slug="doc")
        await pipeline(store, [["OTHER"]]).ingest_pdf(b"%PDF b", "b.pdf", slug="other")
        out = await store.delete_document("doc")
        assert out["slug"] == "doc"
        assert await store.get_index("doc") is None
        assert await store.get_page_text("doc", 1) is None
        assert [d["slug"] for d in await store.list_documents()] == ["other"]
        with pytest.raises(KeyError):
            await store.delete_document("doc")
    asyncio.run(run())


async def _cited_canvas() -> WorkspaceService:
    ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
    await ws.create_workspace("pumps")
    await ws.add_node("pumps", id="card", node_type="document", data={"slug": "doc"})
    await ws.add_node("pumps", id="spec", node_type="spec", data={"rows": [
        {"key": "Max flow", "value": "12", "source_ref": {"slug": "doc", "page": 1}},
        {"key": "Head", "value": "24", "source_ref": {"slug": "other", "page": 1}},
    ]})
    await ws.add_node("pumps", id="note", node_type="markdown",
                      data={"text": "Up to [12](anchor:doc?page=1&quote=12)."})
    await ws.create_workspace("empty")
    return ws


def test_citations_name_each_canvas_and_what_on_it_cites():
    async def run():
        ws = await _cited_canvas()
        assert await find_citations(ws, "doc") == [
            {"canvas": "pumps", "title": "pumps", "cards": 1, "rows": 1, "links": 1},
        ]
        assert await find_citations(ws, "nowhere") == []
    asyncio.run(run())


def test_a_cited_document_is_kept_unless_forced(tmp_path):
    async def run():
        ws = await _cited_canvas()
        store = FsDocStore(tmp_path)
        await pipeline(store, [["PAGE"]]).ingest_pdf(b"%PDF a", "a.pdf", slug="doc")
        refused = await delete_document(ws, store, "doc")
        assert refused["deleted"] is False and refused["cited_by"][0]["canvas"] == "pumps"
        assert await store.get_index("doc") is not None
        done = await delete_document(ws, store, "doc", force=True)
        assert done["deleted"] is True
        assert await store.get_index("doc") is None
        # The canvas keeps its card and rows.
        state = await ws.get_state("pumps")
        assert {n["id"] for n in state["nodes"]} == {"card", "spec", "note"}
    asyncio.run(run())


def test_http_delete_refuses_a_cited_document_and_forces_it():
    s = make_in_memory_services(page_count=1)
    client = TestClient(build_app(
        workspace_service=s.workspace, ingest_service=s.ingest, doc_store=s.doc_store, bus=s.bus,
    ))
    asyncio.run(pipeline(s.doc_store, [["PAGE"]]).ingest_pdf(b"%PDF a", "a.pdf", slug="doc"))
    asyncio.run(s.workspace.create_workspace("pumps"))
    asyncio.run(s.workspace.add_node("pumps", id="card", node_type="document", data={"slug": "doc"}))
    refused = client.delete("/api/documents/doc")
    assert refused.status_code == 409
    assert refused.json()["detail"]["cited_by"][0]["cards"] == 1
    forced = client.delete("/api/documents/doc?force=true")
    assert forced.json()["deleted"] is True
    gone = client.delete("/api/documents/doc")
    assert gone.status_code == 404


def test_mcp_delete_document_is_advertised_as_destructive():
    from anchor.adapters.mcp.server import DELETE_DOCUMENT_TOOL_DEFINITION

    assert DELETE_DOCUMENT_TOOL_DEFINITION["annotations"]["destructiveHint"] is True
    assert "confirm" in DELETE_DOCUMENT_TOOL_DEFINITION["description"]
    json.dumps(DELETE_DOCUMENT_TOOL_DEFINITION)


def test_cli_intent_watch_returns_a_waiting_ask(tmp_path):
    from typer.testing import CliRunner

    from anchor.adapters.cli.main import app
    from anchor.infra.stores.fs_intent_store import FsIntentStore
    from intent_layer.actor import Actor, actor_scope
    from intent_layer.service import IntentService
    from intent_layer.signals import MemoryPendingSignals
    from tests.intent_layer.form_host import FormHost

    data_dir = tmp_path / ".anchor_data"
    # The same store the CLI opens for this data dir.
    service = IntentService(FsIntentStore(data_dir), MemoryPendingSignals(), host=FormHost())
    with actor_scope(Actor(kind="human", label="browser")):
        asyncio.run(service.enqueue("user_request", origin_canvas_id="pumps"))
    out = CliRunner().invoke(app, ["intent", "watch", "--once", "--timeout", "2", "--data-dir", str(data_dir)])
    assert out.exit_code == 0, out.output
    assert json.loads(out.output.strip().splitlines()[-1])["origin_canvas_id"] == "pumps"
