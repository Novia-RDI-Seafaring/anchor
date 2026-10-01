"""Scoped-ask threads (#343): the additive Intent fields, thread items, and
the all-or-nothing apply of staged suggestions through WorkspaceService."""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.clock import FixedClock
from anchor.core.events.actor import Actor, actor_scope
from anchor.core.intents.intent import (
    INTENT_PENDING_EVENT,
    QUESTION_ANSWERED,
    QUESTION_OPEN,
    SUGGESTION_APPLIED,
    SUGGESTION_DECLINED,
    SUGGESTION_PENDING,
    SUGGESTION_SUPERSEDED,
    Intent,
    ThreadItem,
)
from anchor.core.services.intent_service import (
    IntentService,
    SuggestionApplyError,
    ThreadError,
)
from anchor.core.services.workspace_batch import BatchApplyError
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_intent_store import MemoryIntentStore
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore

HUMAN = Actor(kind="human", label="browser")
AGENT = Actor(kind="agent", label="claude")


# -- model round-trip --------------------------------------------------------- #
def test_legacy_record_loads_with_thread_defaults():
    """A record written before #343 carries none of the new keys."""
    raw = {
        "id": "old1",
        "kind": "user_request",
        "origin_canvas_id": "cv",
        "payload": {"text": "hi", "workspace_id": "cv", "node_id": "n1"},
        "status": "pending",
        "created_at": 1.0,
    }
    intent = Intent.from_dict(raw)
    assert intent.targets == []
    assert intent.base_version is None
    assert intent.items == []
    d = intent.to_dict()
    # The wire shape always carries the keys so a client can rely on them.
    assert d["targets"] == [] and d["base_version"] is None and d["items"] == []
    assert d["payload"] == raw["payload"]


def test_thread_round_trip_preserves_items_and_states():
    intent = Intent(
        kind="user_request",
        origin_canvas_id="cv",
        targets=[{"workspace_id": "cv", "node_id": "n1"}],
        base_version=7,
        created_at=1.0,
        items=[
            ThreadItem(type="message", author=HUMAN, text="hi", created_at=1.0),
            ThreadItem(
                type="question", author=AGENT, text="which?", created_at=2.0,
                state=QUESTION_OPEN, answer=None,
            ),
            ThreadItem(
                type="suggestion", author=AGENT, text="add", created_at=3.0,
                state=SUGGESTION_APPLIED, applied_versions=[8, 9], supersedes="x",
                ops=[{"type": "NodeAdded", "payload": {"id": "c1", "label": "A"}}],
            ),
        ],
    )
    back = Intent.from_dict(intent.to_dict())
    assert back.targets == [{"workspace_id": "cv", "node_id": "n1"}]
    assert back.base_version == 7
    assert [i.type for i in back.items] == ["message", "question", "suggestion"]
    assert back.items[0].state is None
    assert back.items[0].author == HUMAN
    assert back.items[1].state == QUESTION_OPEN
    assert back.items[2].applied_versions == [8, 9]
    assert back.items[2].supersedes == "x"
    assert back.items[2].ops == [{"type": "NodeAdded", "payload": {"id": "c1", "label": "A"}}]
    # Wire shape of an item: optional keys only when set; author is the
    # event Actor shape.
    d = back.items[0].to_dict()
    assert set(d) == {"id", "type", "author", "text", "created_at", "state"}
    assert d["author"] == {"kind": "human", "id": None, "label": "browser"}
    assert "ops" in back.items[2].to_dict() and "applied_versions" in back.items[2].to_dict()


def test_item_without_author_loads_as_system():
    item = ThreadItem.from_dict({"id": "i", "type": "message", "text": "x"})
    assert item.author.kind == "system"


# -- service fixtures --------------------------------------------------------- #
def _services():
    bus = MemoryEventBus()
    clock = FixedClock(ts=100.0)
    ws = WorkspaceService(MemoryWorkspaceStore(), bus, clock=clock)
    svc = IntentService(MemoryIntentStore(), bus, now=clock.now, workspace=ws)
    return svc, ws, bus, clock


async def _thread(svc, ws, *, nodes=("n1", "n2"), edge=True):
    await ws.create_workspace("cv")
    for n in nodes:
        await ws.add_node("cv", id=n, label=n.upper(), x=0, y=0)
    if edge and len(nodes) >= 2:
        await ws.add_edge("cv", id="e1", source=nodes[0], target=nodes[1])
    with actor_scope(HUMAN):
        intent = await svc.enqueue(
            "user_request",
            origin_canvas_id="cv",
            payload={"text": "make sense of this"},
            targets=[{"workspace_id": "cv", "node_id": n} for n in nodes],
        )
    return intent


async def _collect(bus, n):
    out = []
    sub = bus.subscribe(None)
    it = sub.__aiter__()
    try:
        for _ in range(n):
            out.append(await asyncio.wait_for(it.__anext__(), timeout=1.0))
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            await aclose()
    return out


# -- create thread ------------------------------------------------------------ #
async def test_enqueue_records_targets_and_base_version():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    assert intent.targets == [
        {"workspace_id": "cv", "node_id": "n1"},
        {"workspace_id": "cv", "node_id": "n2"},
    ]
    # 2 nodes + 1 edge = version 3 when the ask was made.
    assert intent.base_version == 3
    assert (await svc.get(intent.id)).base_version == 3


async def test_enqueue_without_a_canvas_leaves_base_version_none():
    svc, _ws, _bus, _clock = _services()
    intent = await svc.enqueue("user_request", payload={"text": "x"})
    assert intent.base_version is None
    # An unknown canvas is not conjured into being just to read a version.
    intent = await svc.enqueue("user_request", origin_canvas_id="ghost")
    assert intent.base_version is None
    assert [m.slug for m in await _ws.store.list_workspaces()] == []


async def test_enqueue_rejects_malformed_targets():
    svc, _ws, _bus, _clock = _services()
    with pytest.raises(ThreadError) as exc:
        await svc.enqueue("user_request", targets=[{"node_id": "n1"}])
    assert exc.value.code == "invalid_targets"
    with pytest.raises(ThreadError):
        await svc.enqueue("user_request", targets="n1")  # type: ignore[arg-type]


# -- add item ----------------------------------------------------------------- #
async def test_add_item_stamps_author_from_ambient_actor_and_signals():
    svc, ws, bus, clock = _services()
    intent = await _thread(svc, ws)
    clock.advance(1.0)
    with actor_scope(AGENT):
        collect = asyncio.create_task(_collect(bus, 1))
        await asyncio.sleep(0)
        intent, item = await svc.add_item(intent.id, type="message", text="looking")
        events = await collect
    assert item.author == AGENT
    assert item.created_at == 101.0
    assert item.state is None
    assert intent.items[-1].id == item.id
    assert events[0].type == INTENT_PENDING_EVENT and events[0].workspace_id == "cv"


async def test_add_item_types_states_and_validation():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    with actor_scope(AGENT):
        _, q = await svc.add_item(intent.id, type="question", text="which pump?")
        assert q.state == QUESTION_OPEN
        _, s = await svc.add_item(
            intent.id, type="suggestion", text="rename",
            ops=[{"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "P"}}}],
        )
        assert s.state == SUGGESTION_PENDING and s.ops is not None
        _, r = await svc.add_item(intent.id, type="result", text="done")
        assert r.state is None

        with pytest.raises(ThreadError) as exc:
            await svc.add_item(intent.id, type="teleport", text="x")
        assert exc.value.code == "invalid_item"
        with pytest.raises(ThreadError) as exc:
            await svc.add_item(intent.id, type="message", text="   ")
        assert exc.value.code == "invalid_item"
        with pytest.raises(ThreadError) as exc:
            await svc.add_item(intent.id, type="suggestion", text="x", ops=[])
        assert exc.value.code == "invalid_ops"
        with pytest.raises(ThreadError) as exc:
            await svc.add_item(
                intent.id, type="suggestion", text="x",
                ops=[{"type": "NodeMoved", "payload": {"id": "n1"}}],
            )
        assert exc.value.code == "invalid_ops"
        with pytest.raises(ThreadError) as exc:
            await svc.add_item(intent.id, type="message", text="x", ops=[{"type": "NodeRemoved", "payload": {}}])
        assert exc.value.code == "invalid_item"
    with pytest.raises(KeyError):
        await svc.add_item("ghost", type="message", text="x")


async def test_supersedes_marks_earlier_pending_suggestion():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    ops = [{"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "P"}}}]
    with actor_scope(AGENT):
        _, first = await svc.add_item(intent.id, type="suggestion", text="v1", ops=ops)
        intent, second = await svc.add_item(
            intent.id, type="suggestion", text="v2", ops=ops, supersedes=first.id,
        )
        assert intent.find_item(first.id).state == SUGGESTION_SUPERSEDED
        assert second.supersedes == first.id and second.state == SUGGESTION_PENDING
        with pytest.raises(ThreadError) as exc:
            await svc.add_item(intent.id, type="suggestion", text="v3", ops=ops, supersedes="nope")
        assert exc.value.code == "item_not_found"


# -- answer ------------------------------------------------------------------- #
async def test_answer_question():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    with actor_scope(AGENT):
        _, q = await svc.add_item(intent.id, type="question", text="which?")
        _, m = await svc.add_item(intent.id, type="message", text="note")
    with actor_scope(HUMAN):
        intent, answered = await svc.answer_question(intent.id, q.id, text="the left one")
    assert answered.state == QUESTION_ANSWERED and answered.answer == "the left one"
    assert intent.find_item(q.id).answer == "the left one"
    with pytest.raises(ThreadError) as exc:
        await svc.answer_question(intent.id, m.id, text="x")
    assert exc.value.code == "not_a_question"
    with pytest.raises(ThreadError) as exc:
        await svc.answer_question(intent.id, "ghost", text="x")
    assert exc.value.code == "item_not_found"


# -- apply -------------------------------------------------------------------- #
async def test_apply_is_atomic_one_bad_op_applies_nothing():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    before = await ws.get_state("cv")
    with actor_scope(AGENT):
        _, bad = await svc.add_item(
            intent.id, type="suggestion", text="bad",
            ops=[
                {"type": "NodeAdded", "payload": {"id": "c1", "label": "New"}},
                {"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "X"}}},
                {"type": "EdgeAdded", "payload": {"source": "c1", "target": "ghost"}},
            ],
        )
    with actor_scope(HUMAN):
        with pytest.raises(SuggestionApplyError) as exc:
            await svc.apply_suggestion(intent.id, bad.id)
    err = exc.value
    assert err.failing_index == 2
    assert err.stale is True
    assert "ghost" in err.reason
    assert err.to_dict() == {
        "error": "apply_failed", "failing_index": 2, "failing_op_index": 2,
        "reason": err.reason, "stale": True,
    }
    after = await ws.get_state("cv")
    assert after == before  # nothing written, version unchanged
    assert (await svc.get(intent.id)).find_item(bad.id).state == SUGGESTION_PENDING


async def test_apply_maps_client_ids_and_stamps_accepted_review():
    svc, ws, bus, _clock = _services()
    intent = await _thread(svc, ws)
    with actor_scope(AGENT):
        _, item = await svc.add_item(
            intent.id, type="suggestion", text="add a spec, link it, rename n1",
            ops=[
                {"type": "NodeAdded", "payload": {"id": "tmp-spec", "node_type": "spec", "label": "S", "parent": None}},
                {"type": "EdgeAdded", "payload": {"id": "tmp-edge", "source": "n1", "target": "tmp-spec"}},
                {"type": "EdgeUpdated", "payload": {"id": "tmp-edge", "fields": {"label": "has"}}},
                {"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "Pump A"}}},
            ],
        )
    with actor_scope(HUMAN):
        collect = asyncio.create_task(_collect(bus, 4))
        await asyncio.sleep(0)
        intent, applied, result = await svc.apply_suggestion(intent.id, item.id)
        events = await collect
    assert applied.state == SUGGESTION_APPLIED
    assert applied.applied_versions == [4, 5, 6, 7]
    assert result["versions"] == [4, 5, 6, 7]
    assert result["workspace_id"] == "cv"
    real_node = result["id_map"]["tmp-spec"]
    real_edge = result["id_map"]["tmp-edge"]
    assert real_node not in ("tmp-spec", "") and real_edge not in ("tmp-edge", "")

    state = await ws.get_state("cv")
    node = next(n for n in state["nodes"] if n["id"] == real_node)
    assert node["node_type"] == "spec"
    assert node["data"]["review"] == {
        "state": "accepted", "by": {"kind": "human", "label": "browser"}, "at": 100.0,
    }
    edge = next(e for e in state["edges"] if e["id"] == real_edge)
    assert edge["source"] == "n1" and edge["target"] == real_node and edge["label"] == "has"
    assert edge["data"]["review"]["state"] == "accepted"
    assert next(n for n in state["nodes"] if n["id"] == "n1")["label"] == "Pump A"

    # Attribution: every emitted event carries the suggestion's author as
    # actor and the item id as causation, and they went out on the bus.
    assert [e.type for e in events] == ["NodeAdded", "EdgeAdded", "EdgeUpdated", "NodeUpdated"]
    for e in events:
        assert e.actor == AGENT
        assert e.causation_id == item.id
        assert e.workspace_id == "cv"
    # The same is what the event log holds.
    logged = await ws.store.read_events("cv", after_version=3)
    assert [e.version for e in logged] == [4, 5, 6, 7]
    assert all(e.causation_id == item.id and e.actor == AGENT for e in logged)


async def test_apply_removal_cascades_edges_as_system():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)  # n1 -e1-> n2
    with actor_scope(AGENT):
        _, item = await svc.add_item(
            intent.id, type="suggestion", text="drop n2",
            ops=[{"type": "NodeRemoved", "payload": {"id": "n2"}}],
        )
    with actor_scope(HUMAN):
        _, applied, result = await svc.apply_suggestion(intent.id, item.id)
    types = [(e["type"], e["actor"]["kind"]) for e in result["events"]]
    assert types == [("EdgeRemoved", "system"), ("NodeRemoved", "agent")]
    assert applied.applied_versions == [4, 5]
    state = await ws.get_state("cv")
    assert [n["id"] for n in state["nodes"]] == ["n1"] and state["edges"] == []


async def test_apply_detects_stale_when_target_vanished():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    with actor_scope(AGENT):
        _, item = await svc.add_item(
            intent.id, type="suggestion", text="rename",
            ops=[{"type": "NodeUpdated", "payload": {"id": "n2", "fields": {"label": "Z"}}}],
        )
    await ws.remove_node("cv", "n2")  # the human moved on
    with actor_scope(HUMAN), pytest.raises(SuggestionApplyError) as exc:
        await svc.apply_suggestion(intent.id, item.id)
    assert exc.value.stale is True and exc.value.failing_index == 0


async def test_apply_detects_stale_within_the_batch():
    """An op that removes an element makes a later op on it stale, because
    validation runs on the simulated state as the batch progresses."""
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)  # n1 -e1-> n2
    with actor_scope(AGENT):
        _, item2 = await svc.add_item(
            intent.id, type="suggestion", text="double remove",
            ops=[
                {"type": "EdgeRemoved", "payload": {"id": "e1"}},
                {"type": "EdgeRemoved", "payload": {"id": "e1"}},
            ],
        )
    with actor_scope(HUMAN), pytest.raises(SuggestionApplyError) as exc:
        await svc.apply_suggestion(intent.id, item2.id)
    assert exc.value.failing_index == 1 and exc.value.stale is True


async def test_apply_reports_invalid_payload_and_unknown_type():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    with actor_scope(AGENT):
        _, item = await svc.add_item(
            intent.id, type="suggestion", text="bad payload",
            ops=[{"type": "NodeUpdated", "payload": {"id": "n1"}}],  # fields missing
        )
    with actor_scope(HUMAN), pytest.raises(SuggestionApplyError) as exc:
        await svc.apply_suggestion(intent.id, item.id)
    assert exc.value.failing_index == 0 and exc.value.stale is False
    assert "fields" in exc.value.reason
    # The batch layer itself rejects a type the reducer does not know.
    with pytest.raises(BatchApplyError) as bexc:
        await ws.apply_batch(
            "cv", [{"type": "NodeMoved", "payload": {"id": "n1"}}],
            actor=AGENT, causation_id="c", approver=HUMAN,
        )
    assert bexc.value.failing_index == 0 and "unknown op type" in bexc.value.reason


async def test_apply_state_guards():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    ops = [{"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "P"}}}]
    with actor_scope(AGENT):
        _, s = await svc.add_item(intent.id, type="suggestion", text="v1", ops=ops)
        _, m = await svc.add_item(intent.id, type="message", text="note")
    with actor_scope(HUMAN):
        await svc.apply_suggestion(intent.id, s.id)
        with pytest.raises(ThreadError) as exc:
            await svc.apply_suggestion(intent.id, s.id)  # already applied
        assert exc.value.code == "not_pending"
        with pytest.raises(ThreadError) as exc:
            await svc.apply_suggestion(intent.id, m.id)
        assert exc.value.code == "not_a_suggestion"
        with pytest.raises(KeyError):
            await svc.apply_suggestion("ghost", s.id)
    # Without a wired workspace the service says so instead of crashing.
    bare = IntentService(MemoryIntentStore(), MemoryEventBus())
    with pytest.raises(ThreadError) as exc:
        await bare.apply_suggestion(intent.id, s.id)
    assert exc.value.code == "workspace_unavailable"


async def test_resolve_leaves_pending_suggestions_approvable():
    """The agent's flow is "post a result, then resolve"; the human approves
    on their own time. Resolving therefore never touches suggestion state,
    and apply / decline still work on a resolved thread."""
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    ops = [{"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "P"}}}]
    with actor_scope(AGENT):
        _, s1 = await svc.add_item(intent.id, type="suggestion", text="v1", ops=ops)
        _, s2 = await svc.add_item(intent.id, type="suggestion", text="v2", ops=ops)
        await svc.add_item(intent.id, type="result", text="done")
        resolved = await svc.resolve(intent.id, {"ok": True})
    assert resolved.status == "resolved"
    assert [i.state for i in resolved.items if i.type == "suggestion"] == ["pending", "pending"]
    with actor_scope(HUMAN):
        _, applied, _ = await svc.apply_suggestion(intent.id, s1.id)
        _, declined = await svc.decline_suggestion(intent.id, s2.id, comment="no")
    assert applied.state == SUGGESTION_APPLIED and declined.state == SUGGESTION_DECLINED
    assert (await svc.get(intent.id)).status == "resolved"


async def test_open_question_keeps_thread_pending_and_visible():
    """A thread waiting on the human stays in the pending list; the agent
    sees the question is still open (no answer) and moves on."""
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    with actor_scope(AGENT):
        _, q = await svc.add_item(intent.id, type="question", text="which?")
    nxt = await svc.next()
    assert nxt is not None and nxt.id == intent.id
    seen = nxt.find_item(q.id)
    assert seen.state == QUESTION_OPEN and seen.answer is None
    assert seen.to_dict()["state"] == "open" and "answer" not in seen.to_dict()


# -- decline ------------------------------------------------------------------ #
async def test_decline_records_comment_as_message_item():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    ops = [{"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "P"}}}]
    with actor_scope(AGENT):
        _, s = await svc.add_item(intent.id, type="suggestion", text="v1", ops=ops)
    with actor_scope(HUMAN):
        intent, declined = await svc.decline_suggestion(
            intent.id, s.id, comment="wrong pump",
        )
    assert declined.state == SUGGESTION_DECLINED
    last = intent.items[-1]
    assert last.type == "message" and last.text == "wrong pump" and last.author == HUMAN
    # Canvas untouched.
    assert next(n for n in (await ws.get_state("cv"))["nodes"] if n["id"] == "n1")["label"] == "N1"
    with pytest.raises(ThreadError) as exc:
        await svc.decline_suggestion(intent.id, s.id)
    assert exc.value.code == "not_pending"
    # No comment -> no extra item.
    with actor_scope(AGENT):
        _, s2 = await svc.add_item(intent.id, type="suggestion", text="v2", ops=ops)
    intent, _ = await svc.decline_suggestion(intent.id, s2.id)
    assert intent.items[-1].id == s2.id


# -- placed messages: ghosts of work to come (progress on the canvas) --------- #
async def _svc_with_intent():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    return svc, intent


async def test_placed_message_starts_planned_and_round_trips():
    svc, intent = await _svc_with_intent()
    with actor_scope(AGENT):
        _, item = await svc.add_item(
            intent.id, type="message", text="1. adding LKH-5 node",
            place={"x": 355, "y": 391, "width": 351, "height": 182},
        )
    assert item.state == "planned"
    assert item.place == {"x": 355.0, "y": 391.0, "width": 351.0, "height": 182.0}
    # Survives the store, with the place intact.
    again = await svc.get(intent.id)
    assert again.items[0].place == item.place
    assert ThreadItem.from_dict(item.to_dict()).place == item.place


async def test_question_can_offer_options():
    svc, intent = await _svc_with_intent()
    with actor_scope(AGENT):
        _, q = await svc.add_item(
            intent.id, type="question", text="Every other word, or every other row?",
            options=["every other word", "every other row", " every other row "],
        )
    # Kept in order, trimmed, without repeats; still an open question.
    assert q.options == ["every other word", "every other row"]
    assert q.state == "open"
    again = await svc.get(intent.id)
    assert again.items[0].options == q.options
    assert ThreadItem.from_dict(q.to_dict()).options == q.options
    # A press on an option is an ordinary answer.
    with actor_scope(HUMAN):
        _, answered = await svc.answer_question(intent.id, q.id, text="every other row")
    assert answered.answer == "every other row" and answered.state == "answered"


async def test_only_a_question_offers_options():
    svc, intent = await _svc_with_intent()
    with actor_scope(AGENT):
        with pytest.raises(ThreadError) as exc:
            await svc.add_item(intent.id, type="message", text="hi", options=["a"])
        assert exc.value.code == "invalid_item"
        with pytest.raises(ThreadError):
            await svc.add_item(intent.id, type="question", text="?", options=["", "a"])


async def test_message_without_place_has_no_state():
    svc, intent = await _svc_with_intent()
    with actor_scope(AGENT):
        _, item = await svc.add_item(intent.id, type="message", text="fetching page 3")
    assert item.state is None and item.place is None


async def test_place_is_validated_not_coerced():
    svc, intent = await _svc_with_intent()
    with actor_scope(AGENT):
        for bad in ({"x": 1}, {"x": "1", "y": 2}, {"x": 1, "y": float("nan")}, [1, 2], {"x": True, "y": 0}):
            with pytest.raises(ThreadError) as exc:
                await svc.add_item(intent.id, type="message", text="x", place=bad)
            assert exc.value.code == "invalid_item"
        # Only a message or a question can sit on the canvas.
        with pytest.raises(ThreadError):
            await svc.add_item(intent.id, type="result", text="done", place={"x": 0, "y": 0})


async def test_update_item_moves_a_ghost_through_its_states():
    svc, intent = await _svc_with_intent()
    with actor_scope(AGENT):
        _, ghost = await svc.add_item(
            intent.id, type="message", text="2. adding dimensions", place={"x": 0, "y": 0},
        )
        _, active = await svc.update_item(
            intent.id, ghost.id, text="fetching page 3", state="active",
        )
        assert active.state == "active" and active.text == "fetching page 3"
        _, moved = await svc.update_item(intent.id, ghost.id, place={"x": 10, "y": 20})
        assert moved.place == {"x": 10.0, "y": 20.0} and moved.state == "active"
        _, done = await svc.update_item(intent.id, ghost.id, state="done")
        assert done.state == "done"
    # The change is the same item, not a new line in the thread.
    assert len((await svc.get(intent.id)).items) == 1


async def test_update_item_refuses_what_it_should():
    svc, intent = await _svc_with_intent()
    with actor_scope(AGENT):
        _, plain = await svc.add_item(intent.id, type="message", text="note")
        _, sugg = await svc.add_item(intent.id, type="suggestion", text="v1", ops=[
            {"type": "NodeAdded", "payload": {"id": "n9", "label": "N9"}},
        ])
        # A state on a message that has no place means nothing.
        with pytest.raises(ThreadError):
            await svc.update_item(intent.id, plain.id, state="active")
        # A state outside the vocabulary.
        with pytest.raises(ThreadError):
            await svc.update_item(intent.id, plain.id, place={"x": 0, "y": 0}, state="flying")
        # Only messages change in place; a suggestion has its own verbs.
        with pytest.raises(ThreadError):
            await svc.update_item(intent.id, sugg.id, text="v2")
        # Blank text is not an update.
        with pytest.raises(ThreadError):
            await svc.update_item(intent.id, plain.id, text="   ")
        with pytest.raises(KeyError):
            await svc.update_item("nope", plain.id, text="x")
    # Giving a plain message a place makes it a ghost, starting planned.
    with actor_scope(AGENT):
        _, placed = await svc.update_item(intent.id, plain.id, place={"x": 5, "y": 5})
    assert placed.state == "planned"


# -- act, then ask: an applied suggestion can be put back ------------------- #
async def test_apply_records_the_way_back_and_revert_takes_it():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)  # n1 -- e1 --> n2 on cv
    ops = [
        {"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "Renamed"}}},
        {"type": "NodeAdded", "payload": {"id": "c9", "label": "New", "x": 5, "y": 6}},
        {"type": "EdgeAdded", "payload": {"id": "e9", "source": "n1", "target": "c9"}},
        {"type": "NodeRemoved", "payload": {"id": "n2"}},
    ]
    with actor_scope(AGENT):
        _, item = await svc.add_item(intent.id, type="suggestion", text="do it", ops=ops)
        _, item, applied = await svc.apply_suggestion(intent.id, item.id)
    assert item.state == SUGGESTION_APPLIED
    real_c9 = applied["id_map"].get("c9", "c9")
    mid = await ws.get_state("cv")
    assert {n["id"] for n in mid["nodes"]} == {"n1", real_c9}
    assert next(n for n in mid["nodes"] if n["id"] == "n1")["label"] == "Renamed"
    # The way back, in reverse order, naming the ids that were actually used.
    assert [op["type"] for op in item.undo_ops] == [
        "NodeAdded", "EdgeAdded", "EdgeRemoved", "NodeRemoved", "NodeUpdated",
    ]
    assert item.undo_ops[2]["payload"]["id"] == applied["id_map"].get("e9", "e9")
    assert item.undo_ops[3]["payload"]["id"] == real_c9
    assert item.undo_ops[4]["payload"]["fields"] == {"label": "N1"}

    with actor_scope(HUMAN):
        _, item, reverted = await svc.revert_suggestion(intent.id, item.id)
    assert item.state == "reverted"
    after = await ws.get_state("cv")
    assert {n["id"] for n in after["nodes"]} == {"n1", "n2"}
    assert next(n for n in after["nodes"] if n["id"] == "n1")["label"] == "N1"
    # The edge that cascaded away with n2 is back too.
    assert {e["id"] for e in after["edges"]} == {"e1"}
    assert reverted["versions"]


async def test_revert_refuses_what_it_should():
    svc, ws, _bus, _clock = _services()
    intent = await _thread(svc, ws)
    with actor_scope(AGENT):
        _, pending = await svc.add_item(intent.id, type="suggestion", text="v1", ops=[
            {"type": "NodeUpdated", "payload": {"id": "n1", "fields": {"label": "x"}}},
        ])
        _, note = await svc.add_item(intent.id, type="message", text="hi")
    with pytest.raises(ThreadError) as exc:
        await svc.revert_suggestion(intent.id, pending.id)
    assert exc.value.code == "not_applied"
    with pytest.raises(ThreadError):
        await svc.revert_suggestion(intent.id, note.id)
    # Applied before undo existed: refused with a reason, not guessed at.
    # (A record from before this field: cleared through the store, since the
    # service re-reads the thread rather than trusting what it handed out.)
    with actor_scope(AGENT):
        _, item, _ = await svc.apply_suggestion(intent.id, pending.id)
    stored = await svc.get(intent.id)
    stored.find_item(item.id).undo_ops = None
    await svc._store.replace(stored)
    with pytest.raises(ThreadError) as exc:
        await svc.revert_suggestion(intent.id, item.id)
    assert exc.value.code == "no_undo"


async def test_revert_puts_back_the_checks_and_verdicts_it_found():
    """Putting a change back leaves the card as it was, verdicts and all.

    Evidence normally refuses verdicts a caller sends, so writing the old
    rows back used to leave every row stale. The way back is the server's
    own record of the card, so it is restored as it was.
    """
    from copy import deepcopy

    from anchor.adapters.project_runtime import bind_workspace_sources
    from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
    from tests.adapters.test_value_provenance_parity import _input, _regions

    svc, ws, _bus, _clock = _services()
    docs = MemoryDocStore()
    await docs.write_gold_region_file("doc", 1, _regions())
    bind_workspace_sources(ws, docs)
    await ws.create_workspace("cv")
    data = _input("exact")
    data["rows"][0]["review"] = {"state": "accepted", "by": {"kind": "human", "label": "reader"}}
    await ws.add_node("cv", id="spec", node_type="spec", data=data)
    await ws.add_node("cv", id="aside", label="Aside", x=0, y=0,
                      data={"review": {"state": "rejected", "by": {"kind": "human", "label": "reader"}}})
    before = await ws.get_state("cv")
    spec_before = deepcopy(next(n for n in before["nodes"] if n["id"] == "spec")["data"])
    aside_before = deepcopy(next(n for n in before["nodes"] if n["id"] == "aside")["data"])
    assert spec_before["rows"][0]["evidence"]["status"] == "verified"

    with actor_scope(HUMAN):
        intent = await svc.enqueue("user_request", origin_canvas_id="cv", payload={"text": "add +1"},
                                   targets=[{"workspace_id": "cv", "node_id": "spec"}])
    changed = deepcopy(spec_before["rows"])
    changed[0]["value"] = "43"
    ops = [
        {"type": "NodeUpdated", "payload": {"id": "spec", "fields": {
            "data": {"rows": changed, "description": "added 1"}}}},
        {"type": "NodeRemoved", "payload": {"id": "aside"}},
    ]
    with actor_scope(AGENT):
        _, item = await svc.add_item(intent.id, type="suggestion", text="+1", ops=ops)
        _, item, _ = await svc.apply_suggestion(intent.id, item.id)
    mid = await ws.get_state("cv")
    assert next(n for n in mid["nodes"] if n["id"] == "spec")["data"]["rows"][0]["evidence"]["status"] == "stale"

    with actor_scope(HUMAN):
        await svc.revert_suggestion(intent.id, item.id)
    after = await ws.get_state("cv")
    nodes = {n["id"]: n for n in after["nodes"]}
    # The card exactly as it was: the verified check, the reader's verdict,
    # and no trace of the key the change added.
    assert nodes["spec"]["data"] == spec_before
    # A removed element comes back with its own verdict, not a fresh "accepted".
    assert nodes["aside"]["data"] == aside_before
