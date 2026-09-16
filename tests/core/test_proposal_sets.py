"""Proposal sets: reviewing what an agent added in one go, as one thing (#359).

Covers grouping (reason required, members validated and deduped, unknown
elements refused), the whole-set verdict (every member stamped in one
write, exceptions honoured, already-reviewed sets refused), discarding a
rejected set (members removed, edges cascaded), listing and replay.
"""
from __future__ import annotations

import asyncio

from anchor.core.events.actor import Actor, actor_scope
from anchor.core.workspace.proposals import PROPOSAL_SETS_KEY, ProposalSetError
from anchor.core.workspace.workspace import Workspace
from anchor.infra.bus.replay import replay_from_events
from tests.fixtures.services import make_in_memory_services

AGENT = Actor(kind="agent", label="claude-code")
HUMAN = Actor(kind="human", label="browser")


async def _canvas_with_proposals(s):
    """A review-mode canvas with two agent nodes and an edge between them."""
    await s.workspace.create_workspace("w1")
    await s.workspace.set_review_mode("w1", enabled=True)
    with actor_scope(AGENT):
        await s.workspace.add_node("w1", id="a", label="A", x=0, y=0)
        await s.workspace.add_node("w1", id="b", label="B", x=200, y=0)
        await s.workspace.add_edge("w1", id="e1", source="a", target="b")
    return s


# ── Grouping ────────────────────────────────────────────────────────────────

def test_open_groups_members_and_records_who_and_why():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        with actor_scope(AGENT):
            record = await s.workspace.open_proposal_set(
                "w1",
                reason="mindmap of the author guide",
                members=["a", "b", {"kind": "edge", "id": "e1"}],
            )
        assert record["reason"] == "mindmap of the author guide"
        assert record["by"] == {"kind": "agent", "label": "claude-code"}
        assert record["state"] == "open"
        assert record["members"] == [
            {"kind": "node", "id": "a"},
            {"kind": "node", "id": "b"},
            {"kind": "edge", "id": "e1"},
        ]
        # Stored on the canvas, not stamped on the elements.
        state = await s.workspace.store.load("w1")
        assert state.metadata[PROPOSAL_SETS_KEY][0]["id"] == record["id"]
        assert "proposal_set" not in state.nodes["a"].data

    asyncio.run(run())


def test_open_without_a_reason_is_refused():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        try:
            await s.workspace.open_proposal_set("w1", reason="  ", members=["a"])
        except ProposalSetError as exc:
            assert "reason" in exc.message
        else:
            raise AssertionError("expected ProposalSetError")

    asyncio.run(run())


def test_open_refuses_an_element_that_does_not_exist():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        try:
            await s.workspace.open_proposal_set("w1", reason="r", members=["a", "nope"])
        except ProposalSetError as exc:
            assert "nope" in exc.message
        else:
            raise AssertionError("expected ProposalSetError")
        # Nothing was written.
        assert await s.workspace.list_proposal_sets("w1") == []

    asyncio.run(run())


def test_members_can_be_added_later_and_duplicates_are_ignored():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set("w1", reason="r", members=["a"])
        updated = await s.workspace.add_proposal_set_members(
            "w1", record["id"], members=["a", "b"],
        )
        assert updated["members"] == [
            {"kind": "node", "id": "a"},
            {"kind": "node", "id": "b"},
        ]

    asyncio.run(run())


# ── Verdicts ────────────────────────────────────────────────────────────────

def test_accepting_a_set_stamps_every_member_in_one_write():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        with actor_scope(AGENT):
            record = await s.workspace.open_proposal_set(
                "w1", reason="r", members=["a", "b", {"kind": "edge", "id": "e1"}],
            )
        with actor_scope(HUMAN):
            state, envelopes, reviewed = await s.workspace.review_proposal_set(
                "w1", record["id"], verdict="accepted",
            )
        for node_id in ("a", "b"):
            review = state.nodes[node_id].data["review"]
            assert review["state"] == "accepted"
            assert review["by"] == {"kind": "human", "label": "browser"}
        assert state.edges["e1"].data["review"]["state"] == "accepted"
        assert reviewed["state"] == "accepted"
        assert reviewed["reviewed_by"] == {"kind": "human", "label": "browser"}
        # One batch: every event carries the set id as its cause.
        assert {e.causation_id for e in envelopes} == {record["id"]}

    asyncio.run(run())


def test_rejecting_keeps_the_elements_as_feedback():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set("w1", reason="r", members=["a"])
        with actor_scope(HUMAN):
            state, _, reviewed = await s.workspace.review_proposal_set(
                "w1", record["id"], verdict="rejected",
            )
        # The review convention: a rejected node stays, it is the verdict.
        assert state.nodes["a"].data["review"]["state"] == "rejected"
        assert reviewed["discarded"] is False

    asyncio.run(run())


def test_discarding_a_rejected_set_removes_members_and_their_edges():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set(
            "w1", reason="r", members=["a", "b", {"kind": "edge", "id": "e1"}],
        )
        with actor_scope(HUMAN):
            state, envelopes, reviewed = await s.workspace.review_proposal_set(
                "w1", record["id"], verdict="rejected", discard=True,
            )
        assert state.nodes == {}
        assert state.edges == {}
        assert reviewed["discarded"] is True
        # The edge removal that followed from removing node "a" is attributed
        # to the system, not the human who rejected.
        cascades = [e for e in envelopes if e.type == "EdgeRemoved"]
        assert cascades and all(e.actor.kind == "system" for e in cascades)

    asyncio.run(run())


def test_accept_all_but_these():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set("w1", reason="r", members=["a", "b"])
        with actor_scope(HUMAN):
            state, _, _ = await s.workspace.review_proposal_set(
                "w1", record["id"], verdict="accepted", except_ids=["b"],
            )
        assert state.nodes["a"].data["review"]["state"] == "accepted"
        # Untouched: still the agent's proposal.
        assert state.nodes["b"].data["review"]["state"] == "proposed"

    asyncio.run(run())


def test_a_reviewed_set_cannot_be_reviewed_again():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set("w1", reason="r", members=["a"])
        await s.workspace.review_proposal_set("w1", record["id"], verdict="accepted")
        try:
            await s.workspace.review_proposal_set("w1", record["id"], verdict="rejected")
        except ProposalSetError as exc:
            assert "already accepted" in exc.message
        else:
            raise AssertionError("expected ProposalSetError")

    asyncio.run(run())


def test_discard_is_only_for_rejections():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set("w1", reason="r", members=["a"])
        try:
            await s.workspace.review_proposal_set(
                "w1", record["id"], verdict="accepted", discard=True,
            )
        except ProposalSetError as exc:
            assert "rejected" in exc.message
        else:
            raise AssertionError("expected ProposalSetError")

    asyncio.run(run())


def test_a_member_removed_meanwhile_is_skipped():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set("w1", reason="r", members=["a", "b"])
        await s.workspace.remove_node("w1", "a")
        state, _, reviewed = await s.workspace.review_proposal_set(
            "w1", record["id"], verdict="accepted",
        )
        assert "a" not in state.nodes
        assert state.nodes["b"].data["review"]["state"] == "accepted"
        assert reviewed["state"] == "accepted"

    asyncio.run(run())


# ── Listing and replay ──────────────────────────────────────────────────────

def test_list_filters_by_state():
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        open_set = await s.workspace.open_proposal_set("w1", reason="one", members=["a"])
        done = await s.workspace.open_proposal_set("w1", reason="two", members=["b"])
        await s.workspace.review_proposal_set("w1", done["id"], verdict="accepted")
        assert [r["reason"] for r in await s.workspace.list_proposal_sets("w1")] == ["one", "two"]
        still_open = await s.workspace.list_proposal_sets("w1", state="open")
        assert [r["id"] for r in still_open] == [open_set["id"]]

    asyncio.run(run())


def test_sets_survive_replay_from_the_event_log(tmp_path):
    async def run():
        s = await _canvas_with_proposals(make_in_memory_services())
        record = await s.workspace.open_proposal_set("w1", reason="r", members=["a", "b"])
        await s.workspace.review_proposal_set("w1", record["id"], verdict="accepted")
        events = tmp_path / "events.jsonl"
        stored_events = await s.workspace.store.read_events("w1")
        events.write_text(
            "\n".join(e.model_dump_json() for e in stored_events),
            encoding="utf-8",
        )
        replayed = replay_from_events(Workspace(slug="w1"), events)
        stored = replayed.metadata[PROPOSAL_SETS_KEY][0]
        assert stored["state"] == "accepted"
        assert replayed.nodes["a"].data["review"]["state"] == "accepted"

    asyncio.run(run())
