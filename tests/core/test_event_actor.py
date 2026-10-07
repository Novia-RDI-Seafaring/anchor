"""Actor attribution on the event envelope (#322).

Covers: envelope round-trip (with and without actor), the adapter-scoped
ContextVar plumbing, system attribution on remove cascades, layout moves
carrying the caller's actor, and replay of legacy actor-less logs.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.core.events.actor import (
    SYSTEM_ACTOR,
    Actor,
    actor_scope,
    current_actor,
    parse_actor,
    resolve_cli_actor,
)
from anchor.core.events.envelope import DomainEvent
from anchor.core.workspace.workspace import Workspace
from anchor.infra.bus.replay import replay_from_events
from tests.fixtures.services import make_in_memory_services

# ── Envelope round-trip ─────────────────────────────────────────────────────

def test_envelope_round_trips_actor():
    env = DomainEvent(
        workspace_id="w1",
        type="NodeAdded",
        actor=Actor(kind="agent", id="a-1", label="claude-code"),
    )
    back = DomainEvent.model_validate_json(env.model_dump_json())
    assert back.actor is not None
    assert back.actor.kind == "agent"
    assert back.actor.id == "a-1"
    assert back.actor.label == "claude-code"


def test_envelope_round_trips_none_actor():
    env = DomainEvent(workspace_id="w1", type="NodeAdded")
    assert env.actor is None
    back = DomainEvent.model_validate_json(env.model_dump_json())
    assert back.actor is None


def test_legacy_event_json_without_actor_field_deserializes_as_none():
    # A record written before #322 has no `actor` key at all.
    legacy = {
        "id": "ev-1", "ts": 1.0, "version": 1, "workspace_id": "w1",
        "type": "NodeAdded", "payload": {"id": "a"}, "causation_id": None,
    }
    env = DomainEvent(**legacy)
    assert env.actor is None


def test_actor_rejects_unknown_kind():
    with pytest.raises(ValueError):
        Actor(kind="robot")


# ── Context + CLI parsing helpers ───────────────────────────────────────────

def test_actor_scope_sets_and_restores():
    assert current_actor() is None
    with actor_scope(Actor(kind="human", label="browser")):
        got = current_actor()
        assert got is not None and got.label == "browser"
    assert current_actor() is None


def test_parse_actor_kind_and_label():
    assert parse_actor("agent") == Actor(kind="agent")
    assert parse_actor("agent:claude-code") == Actor(kind="agent", label="claude-code")
    with pytest.raises(ValueError):
        parse_actor("robot:c3po")


def test_resolve_cli_actor_precedence():
    assert resolve_cli_actor(None, None) == Actor(kind="human", label="cli")
    assert resolve_cli_actor(None, "1") == Actor(kind="agent")
    assert resolve_cli_actor(None, "claude-code") == Actor(kind="agent", label="claude-code")
    assert resolve_cli_actor("human:alice", "claude-code") == Actor(kind="human", label="alice")


# ── Service-level attribution ───────────────────────────────────────────────

def test_service_stamps_scoped_actor_on_events():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(Actor(kind="agent", label="mcp-agent")):
            _, env = await s.workspace.add_node("w1", id="a", label="A")
        assert env.actor == Actor(kind="agent", label="mcp-agent")
        # Outside any scope the envelope carries no actor (legacy behavior).
        _, env2 = await s.workspace.add_node("w1", id="b", label="B")
        assert env2.actor is None

    asyncio.run(run())


def test_remove_cascade_is_system_but_command_keeps_caller_actor():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        await s.workspace.add_node("w1", id="b")
        await s.workspace.add_edge("w1", id="e1", source="a", target="b")
        with actor_scope(Actor(kind="human", label="browser")):
            _, envelopes = await s.workspace.remove_node("w1", "a")
        by_type = {e.type: e for e in envelopes}
        assert by_type["EdgeRemoved"].actor == SYSTEM_ACTOR
        assert by_type["NodeRemoved"].actor == Actor(kind="human", label="browser")
        # Causation still groups the cascade with its command.
        assert by_type["EdgeRemoved"].causation_id == by_type["NodeRemoved"].causation_id

    asyncio.run(run())


def test_layout_moves_carry_scoped_actor():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", x=0, y=0)
        await s.workspace.add_node("w1", id="b", x=1, y=1)
        await s.workspace.add_node("w1", id="c", x=2, y=2)
        with actor_scope(Actor(kind="agent", label="claude")):
            _, envelopes = await s.workspace.align_nodes("w1", ["a", "b", "c"], "left")
        assert envelopes, "expected at least one NodeMoved"
        assert all(e.actor == Actor(kind="agent", label="claude") for e in envelopes)

    asyncio.run(run())


# ── Legacy log replay ───────────────────────────────────────────────────────

def test_replay_of_actorless_event_log_still_works(tmp_path):
    events = tmp_path / "events.jsonl"
    lines = [
        {  # pre-#322 record: no actor key
            "id": "ev-1", "ts": 1.0, "version": 1, "workspace_id": "w1",
            "type": "NodeAdded",
            "payload": {"id": "a", "node_type": "concept", "label": "A", "x": 0, "y": 0},
        },
        {  # post-#322 record: actor rides along; replay ignores it
            "id": "ev-2", "ts": 2.0, "version": 2, "workspace_id": "w1",
            "type": "NodeMoved", "payload": {"id": "a", "x": 5.0, "y": 6.0},
            "actor": {"kind": "agent", "id": None, "label": "claude-code"},
        },
    ]
    events.write_text("".join(json.dumps(rec) + "\n" for rec in lines))
    state = replay_from_events(Workspace(slug="w1"), events)
    assert state.version == 2
    assert state.nodes["a"].x == 5.0
    assert state.nodes["a"].y == 6.0
    # The tailer path parses full envelopes: both shapes must validate.
    for rec in lines:
        env = DomainEvent(**rec)
        assert (env.actor is None) == ("actor" not in rec)
