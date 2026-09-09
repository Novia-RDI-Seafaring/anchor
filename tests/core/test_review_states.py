"""Review states on canvas nodes (#324).

Covers: the review-mode writer default (agent-created nodes stamped
``proposed``, human/anonymous ones not), the golden off-by-default path
(byte-identical event payloads), caller-supplied review objects winning,
the ``set_review_mode`` toggle (no metadata residue when off), the
malformed-review soft warning, and replay of the new
``WorkspaceMetadataUpdated`` event.
"""
from __future__ import annotations

import asyncio
import json

from anchor.core.events.actor import Actor, actor_scope
from anchor.core.events.canvas import WorkspaceMetadataUpdated
from anchor.core.workspace.review import proposed_review, review_warning
from anchor.core.workspace.workspace import Workspace
from anchor.infra.bus.replay import replay_from_events
from tests.fixtures.services import make_in_memory_services

AGENT = Actor(kind="agent", label="claude-code")
HUMAN = Actor(kind="human", label="browser")


# ── Writer default: review-mode ON ──────────────────────────────────────────

def test_agent_add_node_in_review_mode_is_stamped_proposed():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.set_review_mode("w1", enabled=True)
        with actor_scope(AGENT):
            state, env = await s.workspace.add_node("w1", id="a", label="A")
        review = state.nodes["a"].data["review"]
        assert review["state"] == "proposed"
        assert review["by"] == {"kind": "agent", "label": "claude-code"}
        assert review["at"] == s.clock.now()
        # The stamp rides the event payload too, so SSE clients see it.
        assert env.payload["data"]["review"]["state"] == "proposed"

    asyncio.run(run())


def test_human_add_node_in_review_mode_is_not_stamped():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.set_review_mode("w1", enabled=True)
        with actor_scope(HUMAN):
            state, env = await s.workspace.add_node("w1", id="a", label="A")
        assert "review" not in state.nodes["a"].data
        assert "review" not in env.payload["data"]

    asyncio.run(run())


def test_actorless_add_node_in_review_mode_is_not_stamped():
    # Legacy/direct service calls carry no actor — never guess "agent".
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.set_review_mode("w1", enabled=True)
        state, _env = await s.workspace.add_node("w1", id="a")
        assert "review" not in state.nodes["a"].data

    asyncio.run(run())


def test_caller_supplied_review_object_wins_over_the_stamp():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.set_review_mode("w1", enabled=True)
        supplied = {"state": "accepted", "by": {"kind": "human"}}
        with actor_scope(AGENT):
            state, _env = await s.workspace.add_node(
                "w1", id="a", data={"review": supplied, "note": "x"},
            )
        assert state.nodes["a"].data["review"] == supplied
        assert state.nodes["a"].data["note"] == "x"

    asyncio.run(run())


def test_stamp_preserves_other_supplied_data_keys():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.set_review_mode("w1", enabled=True)
        with actor_scope(AGENT):
            state, _env = await s.workspace.add_node(
                "w1", id="a", data={"description": "hello"},
            )
        d = state.nodes["a"].data
        assert d["description"] == "hello"
        assert d["review"]["state"] == "proposed"

    asyncio.run(run())


# ── Golden path: review-mode OFF (default) ──────────────────────────────────

def test_off_by_default_agent_add_node_payload_is_byte_identical():
    """A workspace that never opted in behaves exactly as before #324:
    the NodeAdded payload for an agent write carries no review key and the
    supplied data round-trips byte-for-byte."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        data = {"description": "hello", "rows": [{"key": "k", "value": "v"}]}
        with actor_scope(AGENT):
            _state, env = await s.workspace.add_node(
                "w1", id="a", label="A", x=1.0, y=2.0, data=data,
            )
        assert json.dumps(env.payload["data"], sort_keys=True) == json.dumps(
            data, sort_keys=True,
        )
        assert "review" not in env.payload["data"]

    asyncio.run(run())


def test_toggling_review_mode_off_leaves_no_metadata_residue():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        state, _ = await s.workspace.set_review_mode("w1", enabled=True)
        assert state.metadata["review_mode"] is True
        state, _ = await s.workspace.set_review_mode("w1", enabled=False)
        # Merge semantics: None deletes the key — metadata is clean again.
        assert "review_mode" not in state.metadata
        # And the writer default is off again.
        with actor_scope(AGENT):
            state, _env = await s.workspace.add_node("w1", id="a")
        assert "review" not in state.nodes["a"].data

    asyncio.run(run())


def test_set_review_mode_emits_metadata_event_with_actor():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        with actor_scope(HUMAN):
            _state, env = await s.workspace.set_review_mode("w1", enabled=True)
        assert env.type == "WorkspaceMetadataUpdated"
        assert env.payload["patch"] == {"review_mode": True}
        assert env.actor == HUMAN

    asyncio.run(run())


# ── proposed_review / review_warning helpers ────────────────────────────────

def test_proposed_review_omits_missing_label():
    r = proposed_review(Actor(kind="agent"), 42.0)
    assert r == {"state": "proposed", "by": {"kind": "agent"}, "at": 42.0}


def test_review_warning_accepts_valid_states_and_absence():
    assert review_warning(None) is None
    assert review_warning({}) is None
    assert review_warning({"other": 1}) is None
    for state in ("proposed", "accepted", "rejected"):
        assert review_warning({"review": {"state": state}}) is None


def test_review_warning_flags_bad_state_and_shape():
    assert "review" in (review_warning({"review": {"state": "maybe"}}) or "")
    assert "review" in (review_warning({"review": "accepted"}) or "")
    # Full payload (add-node): a review object must carry a state.
    assert review_warning({"review": {"by": {"kind": "agent"}}}) is not None


def test_review_warning_partial_patch_semantics():
    # Deleting the object is fine; so is patching a non-state key.
    assert review_warning({"review": None}, partial=True) is None
    assert review_warning({"review": {"at": 1.0}}, partial=True) is None
    # But a state present in the patch must still be valid.
    assert review_warning({"review": {"state": "nope"}}, partial=True) is not None


# ── Verdicts are plain update-node patches ──────────────────────────────────

def test_accept_verdict_via_update_node_overrides_by_and_state():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.set_review_mode("w1", enabled=True)
        with actor_scope(AGENT):
            await s.workspace.add_node("w1", id="a")
        verdict = {
            "review": {
                "state": "accepted",
                "by": {"kind": "human", "label": "browser"},
                "at": 99.0,
            },
        }
        with actor_scope(HUMAN):
            state, _env = await s.workspace.update_node("w1", "a", {"data": verdict})
        review = state.nodes["a"].data["review"]
        assert review["state"] == "accepted"
        # The full by object in the patch replaces both kind and label —
        # no half-merged {kind: human, label: claude-code} hybrid.
        assert review["by"] == {"kind": "human", "label": "browser"}
        assert review["at"] == 99.0

    asyncio.run(run())


# ── Replay of the new event ─────────────────────────────────────────────────

def test_replay_applies_workspace_metadata_updated(tmp_path):
    events = tmp_path / "events.jsonl"
    lines = [
        {
            "id": "ev-1", "ts": 1.0, "version": 1, "workspace_id": "w1",
            "type": "WorkspaceMetadataUpdated",
            "payload": {"patch": {"review_mode": True}},
        },
        {
            "id": "ev-2", "ts": 2.0, "version": 2, "workspace_id": "w1",
            "type": "WorkspaceMetadataUpdated",
            "payload": {"patch": {"review_mode": None}},
        },
    ]
    events.write_text("".join(json.dumps(rec) + "\n" for rec in lines))
    mid = replay_from_events(Workspace(slug="w1"), events)
    assert mid.version == 2
    assert "review_mode" not in mid.metadata

    only_on = tmp_path / "on.jsonl"
    only_on.write_text(json.dumps(lines[0]) + "\n")
    state = replay_from_events(Workspace(slug="w1"), only_on)
    assert state.metadata["review_mode"] is True


def test_metadata_patch_reducer_merges_and_deletes():
    ws = Workspace(slug="w1", metadata={"references": [], "review_mode": True})
    from anchor.core.workspace.reducer import apply

    out = apply(ws, WorkspaceMetadataUpdated(patch={"review_mode": None}))
    assert "review_mode" not in out.metadata
    assert out.metadata["references"] == []  # untouched sibling survives
