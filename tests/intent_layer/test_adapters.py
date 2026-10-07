"""A mounted form inbox across HTTP, MCP and CLI with opaque field IDs."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from intent_layer.actor import Actor
from intent_layer.adapters.cli import create_cli
from intent_layer.adapters.http import create_router
from intent_layer.adapters.mcp import TOOL_NAMES, call_tool, tool_definitions
from intent_layer.fs_store import FsIntentStore
from intent_layer.service import IntentService
from intent_layer.signals import MemoryPendingSignals
from tests.intent_layer.form_host import FormHost

CHANGE = [{"type": "FieldSet", "payload": {"field": "email", "value": "new@example.test"}}]
READER = Actor(kind="human", id="reader", label="form reader")


@pytest.mark.parametrize("adapter", ["http", "mcp", "cli"])
def test_independent_form_inbox_lifecycle(adapter, tmp_path):
    host, signals = FormHost(), MemoryPendingSignals()

    def service():
        return IntentService(FsIntentStore(tmp_path), signals, host=host)

    app = FastAPI()
    app.include_router(create_router(service, lambda: signals, prefix="/form/inbox", default_actor=READER))
    client = TestClient(app)
    cli, runner = create_cli(service, default_actor=READER), CliRunner()

    def invoke(name, **args):
        if adapter == "mcp":
            return json.loads(asyncio.run(call_tool(service(), name, args, actor=READER)))
        if adapter == "cli":
            ident, item_id = args.get("id"), args.get("item_id")
            names = {"list_pending_intents": "list", "next_intent": "next", "get_intent": "show",
                     "resolve_intent": "resolve", "intent_ask": "ask", "intent_add_item": "add-item",
                     "intent_update_item": "update-item", "intent_answer": "answer",
                     "intent_apply": "apply", "intent_revert": "revert", "intent_decline": "decline"}
            argv = [names[name]] + ([ident] if ident else []) + ([item_id] if item_id else [])
            for key, value in args.items():
                if key in {"id", "item_id"} or value is None:
                    continue
                flag = "--origin" if key == "origin_canvas_id" else f"--{key}"
                if key == "options":
                    for option in value:
                        argv += ["--option", option]
                else:
                    argv += [flag, json.dumps(value) if isinstance(value, (dict, list)) else str(value)]
            result = runner.invoke(cli, argv)
            assert result.exit_code == 0, result.output
            return json.loads(result.output)
        root = "/form/inbox"
        if name == "list_pending_intents":
            response = client.get(root)
        elif name == "next_intent":
            pending = client.get(root).json()["intents"]
            return {"intent": pending[0] if pending else None}
        elif name == "get_intent":
            response = client.get(f"{root}/{args['id']}")
        elif name == "intent_ask":
            response = client.post(root, json={"kind": "user_request",
                                               "payload": {"text": args["text"]},
                                               "targets": args["targets"], "origin_canvas_id": args["origin_canvas_id"]})
        elif name == "resolve_intent":
            response = client.post(f"{root}/{args['id']}/resolve", json=args)
        elif name == "intent_add_item":
            response = client.post(f"{root}/{args['id']}/items", json=args)
        elif name == "intent_update_item":
            response = client.patch(f"{root}/{args['id']}/items/{args['item_id']}", json=args)
        else:
            verb = name.removeprefix("intent_")
            response = client.post(f"{root}/{args['id']}/items/{args['item_id']}/{verb}", json=args)
        assert response.status_code == 200, response.text
        return response.json()

    intent = invoke("intent_ask", text="Check email", origin_canvas_id="signup", targets=["email"])["intent"]
    ident = intent["id"]
    assert intent["targets"] == ["email"] and intent["base_version"] == 0
    assert invoke("list_pending_intents")["intents"][0]["id"] == ident
    assert invoke("next_intent")["intent"]["id"] == ident
    message = invoke("intent_add_item", id=ident, type="message", text="Checking", place={"x": 1, "y": 2})["item"]
    assert message["author"] == READER.model_dump()
    assert invoke("intent_update_item", id=ident, item_id=message["id"], state="done")["item"]["state"] == "done"
    question = invoke("intent_add_item", id=ident, type="question", text="Which?", options=["Work", "Home"])["item"]
    assert invoke("intent_answer", id=ident, item_id=question["id"], text="Work")["item"]["answer"] == "Work"
    suggestion = invoke("intent_add_item", id=ident, type="suggestion", ops=CHANGE)["item"]
    applied = invoke("intent_apply", id=ident, item_id=suggestion["id"])
    assert applied["applied"] == {"form": "signup", "revision": 1}
    assert applied["item"]["undo_ops"][0]["payload"]["value"] == "old@example.test"
    assert host.contexts[0].author == host.contexts[0].approver == READER
    assert host.contexts[0].item_id == suggestion["id"]
    assert host.fields["email"] == "new@example.test"
    assert invoke("intent_revert", id=ident, item_id=suggestion["id"])["item"]["state"] == "reverted"
    assert host.fields["email"] == "old@example.test"
    rejected = invoke("intent_add_item", id=ident, type="suggestion", ops=CHANGE)["item"]
    assert invoke("intent_decline", id=ident, item_id=rejected["id"], comment="Keep old")["item"]["state"] == "declined"
    invoke("resolve_intent", id=ident, result={"checked": True})
    assert invoke("list_pending_intents")["intents"] == []
    assert invoke("get_intent", id=ident)["intent"]["status"] == "resolved"
    assert client.get("/form/inbox/all").json()["intents"][0]["id"] == ident


def test_generic_tool_schemas_do_not_require_canvas_vocabulary():
    definitions = tool_definitions(target_schema={"type": "string"})
    assert {tool["name"] for tool in definitions} == TOOL_NAMES
    ask = next(tool for tool in definitions if tool["name"] == "intent_ask")["inputSchema"]
    assert ask["properties"]["targets"]["items"] == {"type": "string"}
    assert "workspace_slug" not in ask["properties"]
    assert "NodeAdded" not in json.dumps(definitions)


async def test_generic_sse_initial_snapshot_live_count_and_cleanup(tmp_path):
    from types import SimpleNamespace

    host, signals = FormHost(), MemoryPendingSignals()
    service = IntentService(FsIntentStore(tmp_path), signals, host=host)
    router = create_router(lambda: service, lambda: signals)
    route = next(route.endpoint for route in router.routes if route.name == "events")

    async def connected():
        return False

    response = await route(SimpleNamespace(is_disconnected=connected), None, service, signals)
    stream = response.body_iterator
    first = await anext(stream)
    assert first == {"event": "intent_pending", "data": '{"count": 0}'}
    await service.enqueue("user_request", targets=["email"], payload={"private": "never streamed"})
    live = await asyncio.wait_for(anext(stream), 1)
    assert live == {"event": "intent_pending", "data": '{"count": 1}'}
    await stream.aclose()
    assert not signals._queues


async def test_sse_subscribes_before_snapshot_and_cleans_up_snapshot_failure():
    from types import SimpleNamespace

    signals = MemoryPendingSignals()

    class BrokenSnapshot:
        async def list_pending(self, **kwargs):
            assert signals._queues, "listener must be active before reading the snapshot"
            raise RuntimeError("store unavailable")

    service = BrokenSnapshot()
    router = create_router(lambda: service, lambda: signals)
    route = next(route.endpoint for route in router.routes if route.name == "events")
    response = await route(SimpleNamespace(), None, service, signals)
    with pytest.raises(RuntimeError, match="store unavailable"):
        await anext(response.body_iterator)
    assert not signals._queues


async def test_anchor_signal_bridge_preserves_wire_scope_timestamp_and_filters():
    from anchor.core.events.envelope import DomainEvent
    from anchor.core.ids import validate_workspace_slug
    from anchor.core.services.anchor_pending_signals import AnchorPendingSignals
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from intent_layer.signals import PendingSignal

    bus = MemoryEventBus()
    bridge = AnchorPendingSignals(bus)
    stream = bridge.subscribe()
    waiting = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    await bus.publish(DomainEvent(workspace_id="cv", type="NodeAdded", payload={"private": "not a nudge"}))
    await bridge.publish(PendingSignal(None, 3, 12.0))
    assert await asyncio.wait_for(waiting, 1) == PendingSignal("_project", 3, 12.0)
    # The legacy sentinel is a valid canvas slug, so decoding it to None
    # would erase a real canvas origin. Preserve the existing wire scope.
    assert validate_workspace_slug("_project") == "_project"
    next_signal = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    await bridge.publish(PendingSignal("cv", 4, 13.0))
    assert await asyncio.wait_for(next_signal, 1) == PendingSignal("cv", 4, 13.0)
    await stream.aclose()
    assert bus._subscribers == []


@pytest.mark.parametrize("with_outer_actor", [False, True])
async def test_http_restores_actor_across_sequential_same_task_requests_and_errors(tmp_path, with_outer_actor):
    import httpx

    from intent_layer.actor import actor_scope, current_actor

    signals, host = MemoryPendingSignals(), FormHost()
    service = IntentService(FsIntentStore(tmp_path), signals, host=host)
    app = FastAPI()
    app.include_router(create_router(lambda: service, lambda: signals,
                                     prefix="/form/inbox", default_actor=READER))
    outer = Actor(kind="human", id="host-context", label="host") if with_outer_actor else None
    agent = Actor(kind="agent", id="first-body", label="body agent")
    # ASGITransport invokes the app in the caller task. A ContextVar assignment
    # without an explicit finally/reset would leak into the second request.
    with actor_scope(outer):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://form.test") as client:
            intent = (await client.post("/form/inbox", json={"kind": "user_request", "targets": ["email"]})).json()["intent"]
            assert current_actor() is outer
            endpoint = f"/form/inbox/{intent['id']}/items"
            first = await client.post(endpoint, json={"type": "message", "text": "First",
                                                       "actor": agent.model_dump()})
            assert first.json()["item"]["author"] == agent.model_dump()
            assert current_actor() is outer
            second = await client.post(endpoint, json={"type": "message", "text": "Second"})
            assert second.json()["item"]["author"] == (outer or READER).model_dump()
            assert current_actor() is outer
            failure = await client.post(endpoint, json={"type": "question", "text": "",
                                                         "actor": agent.model_dump()})
            assert failure.status_code == 400
            assert current_actor() is outer


@pytest.mark.parametrize("failure_type", [RuntimeError, asyncio.CancelledError])
async def test_http_actor_scope_restores_on_unhandled_host_error_or_cancellation(tmp_path, failure_type):
    import httpx

    from intent_layer.actor import actor_scope, current_actor

    host, signals = FormHost(), MemoryPendingSignals()
    service = IntentService(FsIntentStore(tmp_path), signals, host=host)
    intent = await service.enqueue("user_request", targets=["email"])
    outer = Actor(kind="human", id="outer-host")
    agent = Actor(kind="agent", id="body-agent")

    def abort(_ops):
        assert current_actor() == agent
        raise failure_type()

    host.validate_ops = abort
    app = FastAPI()
    app.include_router(create_router(lambda: service, lambda: signals))
    with actor_scope(outer):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://form.test") as client:
            with pytest.raises(failure_type):
                await client.post(f"/api/intents/{intent.id}/items", json={
                    "type": "suggestion", "ops": CHANGE, "actor": agent.model_dump(),
                })
            assert current_actor() is outer
