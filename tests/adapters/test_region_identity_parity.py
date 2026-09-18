"""All harness transports expose the same page identity rejection."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from anchor.adapters.cli.main import app as cli_app
from anchor.adapters.http.app import build_app
from anchor.extensions.anchor_pdfs import mcp_handlers
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from tests.extensions.anchor_pdfs.test_replacement_generations import harness, pipeline, submit_all
from tests.fixtures.services import make_in_memory_services


@pytest.mark.parametrize("transport", ["http", "mcp", "cli"])
@pytest.mark.parametrize("operation", ["submit", "finalize"])
def test_duplicate_identity_errors_reach_every_transport(tmp_path, monkeypatch, transport, operation):
    store = FsDocStore(tmp_path)
    svc = harness(store, tmp_path, [["One"], ["Two"]])
    order = asyncio.run(svc.ingest_begin(b"source", "doc.pdf"))
    sid = order["session_id"]
    region = {"id": "r1", "kind": "text", "title": "Two", "member_item_ids": ["p2-i0"]}
    payload = {"regions": [region, deepcopy(region)]}
    if operation == "finalize":
        asyncio.run(submit_all(svc, order))
        raw = json.loads(asyncio.run(svc.sessions.read_text(sid, "gold/pages/2.regions.json")))
        raw["regions"].append(deepcopy(raw["regions"][0]))
        asyncio.run(svc.sessions.write_text(sid, "gold/pages/2.regions.json", json.dumps(raw)))
    if transport == "http":
        services = make_in_memory_services()
        app = build_app(workspace_service=services.workspace, doc_store=store,
                        ingest_service=pipeline(store, []), bus=svc.bus, ingest_session_service=svc)
        with TestClient(app) as client:
            if operation == "submit":
                response = client.put(f"/api/ingest/sessions/{sid}/pages/2", json=payload)
            else:
                response = client.post(f"/api/ingest/sessions/{sid}/finalize", json={})
            assert response.status_code == 200
            result = response.json()
    elif transport == "mcp":
        tool = "ingest_submit_page" if operation == "submit" else "ingest_finalize"
        args = {"session_id": sid, **({"page": 2, **payload} if operation == "submit" else {})}
        result = json.loads(asyncio.run(mcp_handlers.call_tool(
            pipeline(store, []), store, tool, args, ingest_session=svc,
        )))
    else:
        import anchor.adapters.cli.ingest_session as commands

        monkeypatch.setattr(commands, "_build_session_services", lambda _: (None, svc))
        if operation == "submit":
            submission = tmp_path / "submission.json"
            submission.write_text(json.dumps(payload), encoding="utf-8")
            args = ["submit-page", sid, "2", "--file", str(submission)]
        else:
            args = ["finalize", sid]
        output = CliRunner().invoke(cli_app, ["ingest-session", *args])
        assert output.exit_code == 1, output.output
        result = json.loads(output.output)
    assert not result["accepted" if operation == "submit" else "finalized"]
    assert result["errors"] == [{
        "region_index": 1, "field": "id", "message": "duplicate region id 'r1' on page 2",
        "code": "duplicate_region_id", "region_id": "r1", "page": 2,
    }]
    assert not asyncio.run(store.has_gold("doc"))
    assert asyncio.run(store.get_embeddings("doc")) is None
