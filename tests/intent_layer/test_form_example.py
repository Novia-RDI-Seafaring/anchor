"""Exercise the runnable example with real router, store, host and signals."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from intent_layer.actor import Actor
from intent_layer.errors import ThreadError
from intent_layer.ports import ThreadContext

SOURCE = Path(__file__).resolve().parents[2] / "examples" / "intent-layer" / "form_backend.py"
SPEC = importlib.util.spec_from_file_location("form_backend_example", SOURCE)
assert SPEC and SPEC.loader
EXAMPLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXAMPLE)


def test_real_form_http_apply_revert_and_opaque_capture_payload():
    with TestClient(EXAMPLE.create_app()) as client:
        before = client.get("/form/state").json()
        assert before == {"fields": {"email": "old@example.test", "max_flow": 42.0}, "revision": 0}
        payload = {"text": "Update selected values", "screenshot": {"capture": "browser-tab",
                   "mime": "image/png", "dataUrl": "data:image/png;base64,fixture"},
                   "dom_targets": [{"id": "email", "tag": "INPUT"}]}
        created = client.post("/form/inbox", json={"kind": "user_request", "origin_canvas_id": "signup",
                              "targets": ["email", "max_flow"], "payload": payload}).json()["intent"]
        ident = created["id"]
        assert created["payload"] == payload
        assert created["targets"] == ["email", "max_flow"]
        assert created["base_version"] == 0
        reply = client.post(f"/form/demo-reply/{ident}").json()
        question = reply["intent"]["items"][-2]
        suggestion = reply["item"]
        assert suggestion["author"]["id"] == "form-demo"
        answered = client.post(f"/form/inbox/{ident}/items/{question['id']}/answer", json={"text": "Yes"})
        assert answered.status_code == 200
        route = f"/form/inbox/{ident}/items/{suggestion['id']}"
        applied = client.post(route + "/apply", json={"actor": {"kind": "human", "id": "reader"}})
        assert applied.status_code == 200, applied.text
        assert client.get("/form/state").json() == {
            "fields": {"email": "work@example.test", "max_flow": 99.0}, "revision": 1}
        restored = client.post(route + "/revert", json={})
        assert restored.status_code == 200, restored.text
        assert client.get("/form/state").json() == {**before, "revision": 2}
        assert client.get(f"/form/inbox/{ident}").json()["intent"]["payload"] == payload


@pytest.mark.parametrize("value", [True, -1, "99", None, 10**400])
def test_real_http_rejects_bad_typed_ops_without_mutation(value):
    with TestClient(EXAMPLE.create_app()) as client:
        ident = client.post("/form/inbox", json={"kind": "user_request", "origin_canvas_id": "signup",
                             "targets": ["max_flow"]}).json()["intent"]["id"]
        before = client.get("/form/state").json()
        response = client.post(f"/form/inbox/{ident}/items", json={"type": "suggestion", "ops": [
            {"type": "FieldSet", "payload": {"field": "max_flow", "value": value}}]})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_ops"
        assert client.get("/form/state").json() == before
        assert client.get(f"/form/inbox/{ident}").json()["intent"]["items"] == []


@pytest.mark.asyncio
async def test_host_batch_undo_repeated_field_and_atomic_rejection():
    host = EXAMPLE.FormHost()
    actor = Actor(kind="human", label="tester")
    context = ThreadContext("thread", "signup", ["email"], "item", actor, actor)
    ops = [{"type": "FieldSet", "payload": {"field": "email", "value": value}}
           for value in ["first@example.test", "second@example.test"]]
    result = await host.apply(context, ops)
    assert host.fields["email"] == "second@example.test"
    await host.revert(context, result.undo)
    assert host.fields["email"] == "old@example.test"
    before = dict(host.fields), host.revision
    with pytest.raises(ThreadError):
        await host.apply(context, ops + [{"type": "FieldSet", "payload": {"field": "max_flow", "value": 8}}])
    assert (host.fields, host.revision) == before
    for bad in [float("nan"), float("inf"), {"field": []}]:
        with pytest.raises(ThreadError):
            host.validate_ops([{"type": "FieldSet", "payload": {"field": "max_flow", "value": bad}}])
    with pytest.raises(ThreadError):
        host.validate_ops([{"type": "FieldSet", "payload": {"field": [], "value": 1}}])


def test_demo_missing_thread_and_invalid_origin():
    with TestClient(EXAMPLE.create_app()) as client:
        assert client.post("/form/demo-reply/missing").status_code == 404
        invalid = client.post("/form/inbox", json={"kind": "user_request", "origin_canvas_id": "other",
                              "targets": ["email"]})
        assert invalid.status_code == 400
        assert client.get("/form/state").json()["revision"] == 0
