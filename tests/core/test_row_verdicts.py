"""A row's verdict on its reference is a person's to give.

An agent's write neither sets nor changes a row's ``review``. A verdict a
person left stays on a row that still makes the same claim from the same
source, and goes when the claim changes.
"""
from __future__ import annotations

import asyncio

from anchor.core.events.actor import Actor, actor_scope
from tests.fixtures.services import make_in_memory_services

AGENT = Actor(kind="agent", label="claude-code")
HUMAN = Actor(kind="human", label="browser")
REF = {"slug": "px", "page": 2}
ACCEPTED = {"state": "accepted", "by": {"kind": "human", "label": "browser"}}


def _row(value: str = "6 bar", review: dict | None = None) -> dict:
    row = {"key": "Max inlet pressure", "value": value, "source_ref": REF}
    return {**row, "review": review} if review else row


async def _rows(s) -> list[dict]:
    state = await s.workspace.get_state("w1")
    return next(n for n in state["nodes"] if n["id"] == "spec")["data"]["rows"]


async def _spec(s, rows: list[dict], actor: Actor) -> None:
    await s.workspace.create_workspace("w1")
    with actor_scope(actor):
        await s.workspace.add_node("w1", id="spec", node_type="spec", label="PX-5", x=0, y=0,
                                   data={"rows": rows})


def test_an_agent_cannot_verify_a_row():
    async def run():
        s = make_in_memory_services()
        await _spec(s, [_row(review=ACCEPTED)], AGENT)
        assert "review" not in (await _rows(s))[0]
        with actor_scope(AGENT):
            await s.workspace.update_node("w1", "spec", {"data": {"rows": [_row(review=ACCEPTED)]}})
        assert "review" not in (await _rows(s))[0]
    asyncio.run(run())


def test_a_person_verifies_and_an_agent_rewrite_keeps_it():
    async def run():
        s = make_in_memory_services()
        await _spec(s, [_row()], AGENT)
        with actor_scope(HUMAN):
            await s.workspace.update_node("w1", "spec", {"data": {"rows": [_row(review=ACCEPTED)]}})
        assert (await _rows(s))[0]["review"]["state"] == "accepted"
        # An agent resending the same row without the verdict, or with
        # another one, leaves the person's verdict as it was.
        rejected = {"state": "rejected", "by": {"kind": "human"}}
        for row in (_row(), _row(review=rejected)):
            with actor_scope(AGENT):
                await s.workspace.update_node("w1", "spec", {"data": {"rows": [row]}})
            assert (await _rows(s))[0]["review"] == ACCEPTED
    asyncio.run(run())


def test_a_changed_claim_drops_the_verdict():
    async def run():
        s = make_in_memory_services()
        await _spec(s, [_row(review=ACCEPTED)], HUMAN)
        with actor_scope(AGENT):
            await s.workspace.update_node("w1", "spec", {"data": {"rows": [_row("10 bar")]}})
        assert "review" not in (await _rows(s))[0]
    asyncio.run(run())
