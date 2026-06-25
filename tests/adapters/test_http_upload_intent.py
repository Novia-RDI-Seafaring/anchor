"""Drop-to-ingest enqueues a drop_to_ingest intent in a harness project (#148).

The server-side ingest path is unchanged for keyed providers. When the project's
provider is ``harness`` (the agent runs the vision extraction, no server key),
the upload route cannot ingest gold itself, so it marks the placeholder node
"awaiting agent" and enqueues a project-level drop_to_ingest intent instead.
"""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.infra.config import AnchorConfig
from tests.fixtures.services import make_in_memory_services

_PDF = b"%PDF-1.4 fake bytes"


def _client(provider: str | None):
    s = make_in_memory_services()
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
        intent_service=s.intents,
        config=AnchorConfig(data_dir="/tmp/anchor-test", provider=provider),
    )
    asyncio.run(s.workspace.create_workspace("cv", "Canvas"))
    return TestClient(app), s


def _upload(client):
    return client.post(
        "/api/workspaces/cv/upload",
        files={"file": ("pump.pdf", _PDF, "application/pdf")},
        data={"x": "10", "y": "20"},
    )


def test_harness_project_enqueues_intent_and_awaits_agent():
    client, s = _client(provider="harness")
    resp = _upload(client).json()
    assert resp["status"] == "awaiting_agent"
    assert resp["intent_id"]

    # A drop_to_ingest intent is now pending, carrying the doc + node.
    pending = asyncio.run(s.intents.list_pending())
    assert len(pending) == 1
    intent = pending[0]
    assert intent.kind == "drop_to_ingest"
    assert intent.origin_canvas_id == "cv"
    assert intent.payload["slug"] == "pump"
    assert intent.payload["node_id"]
    assert intent.payload["workspace_id"] == "cv"

    # The placeholder node reflects "awaiting agent", not pipeline-queued.
    state = asyncio.run(s.workspace.get_state("cv"))
    node = next(n for n in state["nodes"] if n["data"].get("slug") == "pump")
    assert node["data"]["status"] == "awaiting_agent"

    # And the raw PDF was stashed to bronze so the agent can fetch it later.
    # (The memory store keys bronze by filename; the fs store exposes a path.)
    assert "pump.pdf" in s.doc_store._bronze


def test_keyed_project_does_not_enqueue_intent():
    # A non-harness provider keeps the existing direct-ingest path: no intent.
    client, s = _client(provider="openai")
    resp = _upload(client).json()
    assert resp["status"] == "started"
    assert resp.get("intent_id") is None
    assert asyncio.run(s.intents.list_pending()) == []
