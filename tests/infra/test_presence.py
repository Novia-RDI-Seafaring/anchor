"""PresenceTracker — roster join/leave broadcasts + write-derived agent presence."""
from __future__ import annotations

from anchor.core.clock import FixedClock
from anchor.core.events.actor import Actor
from anchor.core.events.envelope import DomainEvent
from anchor.infra.presence import PresenceTracker, fetch_presence


def _evt(ws: str = "w1", actor: Actor | None = None) -> DomainEvent:
    return DomainEvent(workspace_id=ws, type="NodeAdded", payload={"id": "n1"}, actor=actor)


def _tracker(ts: float = 1000.0) -> tuple[PresenceTracker, FixedClock]:
    clock = FixedClock(ts)
    return PresenceTracker(clock=clock.now, write_ttl=90.0), clock


async def test_connect_yields_roster_entry_and_broadcasts_to_others():
    tracker, _ = _tracker()
    id_a, queue_a = tracker.connect("w1", kind="human", label="browser")

    roster = tracker.roster("w1")
    assert len(roster) == 1
    assert roster[0]["client_id"] == id_a
    assert roster[0]["kind"] == "human"
    assert roster[0]["label"] == "browser"
    assert roster[0]["via"] == "sse"
    # No listeners besides the joiner (who is excluded): nothing queued.
    assert queue_a.empty()

    id_b, queue_b = tracker.connect("w1", kind="human", label="monitor")
    # A's queue got the updated two-entry roster; B (the joiner) did not.
    payload = queue_a.get_nowait()
    assert payload["workspace"] == "w1"
    assert {e["client_id"] for e in payload["present"]} == {id_a, id_b}
    assert queue_b.empty()


async def test_disconnect_broadcasts_shrunken_roster():
    tracker, _ = _tracker()
    id_a, queue_a = tracker.connect("w1")
    id_b, _queue_b = tracker.connect("w1", label="monitor")
    queue_a.get_nowait()  # drain B's join

    tracker.disconnect("w1", id_b)
    payload = queue_a.get_nowait()
    assert [e["client_id"] for e in payload["present"]] == [id_a]
    # Unknown ids and empty workspaces are no-ops.
    tracker.disconnect("w1", "nope")
    tracker.disconnect("w2", id_a)
    assert queue_a.empty()


async def test_workspaces_are_isolated():
    tracker, _ = _tracker()
    _id_a, queue_a = tracker.connect("w1")
    tracker.connect("w2", label="other")
    assert queue_a.empty()
    assert len(tracker.roster("w1")) == 1
    assert len(tracker.roster("w2")) == 1


async def test_agent_write_joins_roster_and_broadcasts():
    tracker, clock = _tracker()
    _id_a, queue_a = tracker.connect("w1")

    tracker.note_event(_evt(actor=Actor(kind="agent", label="claude-code")))
    payload = queue_a.get_nowait()
    writers = [e for e in payload["present"] if e["via"] == "writes"]
    assert len(writers) == 1
    assert writers[0]["kind"] == "agent"
    assert writers[0]["label"] == "claude-code"
    assert writers[0]["connected_at"] == clock.now()
    assert writers[0]["last_write_at"] == clock.now()

    # A follow-up write inside the window refreshes silently (membership
    # unchanged, so clients need no new roster).
    clock.advance(30)
    tracker.note_event(_evt(actor=Actor(kind="agent", label="claude-code")))
    assert queue_a.empty()
    writers = [e for e in tracker.roster("w1") if e["via"] == "writes"]
    assert writers[0]["connected_at"] == 1000.0
    assert writers[0]["last_write_at"] == 1030.0


async def test_agent_presence_expires_after_ttl():
    tracker, clock = _tracker()
    _id_a, queue_a = tracker.connect("w1")
    tracker.note_event(_evt(actor=Actor(kind="agent", label="claude-code")))
    queue_a.get_nowait()

    # Inside the window: still present. Past it: gone from the roster.
    clock.advance(90)
    assert any(e["via"] == "writes" for e in tracker.roster("w1"))
    clock.advance(1)
    assert not any(e["via"] == "writes" for e in tracker.roster("w1"))

    # sweep() drops the entry and pushes the shrunken roster.
    tracker.sweep("w1")
    payload = queue_a.get_nowait()
    assert all(e["via"] != "writes" for e in payload["present"])

    # A write after expiry re-joins with a fresh connected_at.
    tracker.note_event(_evt(actor=Actor(kind="agent", label="claude-code")))
    payload = queue_a.get_nowait()
    writer = next(e for e in payload["present"] if e["via"] == "writes")
    assert writer["connected_at"] == clock.now()


async def test_non_agent_actors_do_not_register_write_presence():
    tracker, _ = _tracker()
    tracker.note_event(_evt(actor=None))
    tracker.note_event(_evt(actor=Actor(kind="human", label="browser")))
    tracker.note_event(_evt(actor=Actor(kind="system")))
    assert tracker.roster("w1") == []


async def test_distinct_agents_are_distinct_entries():
    tracker, _ = _tracker()
    tracker.note_event(_evt(actor=Actor(kind="agent", label="claude-code")))
    tracker.note_event(_evt(actor=Actor(kind="agent", label="copilot")))
    labels = {e["label"] for e in tracker.roster("w1")}
    assert labels == {"claude-code", "copilot"}


async def test_roster_sorted_by_arrival():
    tracker, clock = _tracker()
    tracker.note_event(_evt(actor=Actor(kind="agent", label="early")))
    clock.advance(5)
    tracker.connect("w1", label="browser")
    roster = tracker.roster("w1")
    assert [e.get("label") for e in roster] == ["early", "browser"]


def test_fetch_presence_without_serve_returns_note(monkeypatch, tmp_path):
    import anchor.infra.serve_registry as serve_registry

    monkeypatch.setattr(serve_registry, "find_serve_for_data_dir", lambda _d: None)
    result = fetch_presence(tmp_path, "w1")
    assert result["present"] == []
    assert result["serve"] is None
    assert "no running" in result["note"]
