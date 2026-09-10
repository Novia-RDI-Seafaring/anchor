"""Live presence: who is on a canvas right now.

Presence closes the trust gap from #322/#330: a live test session watched
nodes appear and move on its canvas and logged them as possible tool bugs,
because nothing said another party was present. The tracker answers "who
is here" two ways:

- **Connections** — every SSE subscriber to a workspace's event stream
  registers here with an actor kind + label (the web UI is
  ``human``/"browser", the monitor view ``human``/"monitor"). Joining and
  leaving broadcasts the full current roster to every subscriber, so
  clients stay stateless: each ``presence`` event replaces what they knew.
- **Recent writes** — agents (MCP, scripted CLI) don't hold SSE
  connections, so an agent whose writes carry an ``agent`` actor (#322)
  counts as present for :data:`WRITE_PRESENCE_TTL` seconds after its last
  write. These entries are marked ``via: "writes"`` and expire on a
  rolling window; the HTTP server feeds the tracker from its event bus.

Presence is ephemeral by definition: nothing here is persisted, and the
roster lives **in the memory of one serve process**. With several
``anchor serve`` processes bound to the same project, each sees only its
own SSE clients (plus write-derived agents whose events reach its bus) —
cross-process presence is deliberately out of scope. Non-SSE consumers
read the same roster via ``GET /api/workspaces/{slug}/presence``;
:func:`fetch_presence` resolves the running serve for a data dir and
queries it, which is how the MCP tool and the CLI get parity.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from anchor.core.events.envelope import DomainEvent

#: Seconds an agent write keeps its author on the roster.
WRITE_PRESENCE_TTL = 90.0


class PresenceTracker:
    """In-memory, per-process roster of who is on each workspace.

    Single event loop only: every method is called from the serving
    process's loop (SSE handlers, the bus feed task, timer callbacks),
    so plain dicts need no locking. ``clock`` is injectable for tests.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        write_ttl: float = WRITE_PRESENCE_TTL,
    ) -> None:
        self._clock = clock
        self._write_ttl = write_ttl
        # workspace -> client_id -> {queue, kind, label, connected_at}
        self._connections: dict[str, dict[str, dict[str, Any]]] = {}
        # workspace -> (kind, id, label) -> {kind, id, label, connected_at, last_write_at}
        self._writers: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {}
        # workspace -> pending expiry-sweep timer
        self._sweep_handles: dict[str, asyncio.TimerHandle] = {}

    # -- connections ------------------------------------------------------ #
    def connect(
        self, workspace: str, *, kind: str = "human", label: str | None = "browser"
    ) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        """Register one SSE subscriber; returns its id + presence queue.

        The queue receives one full-roster payload per roster change. The
        caller is expected to send the joiner its initial roster itself
        (so it can mark "you"); this broadcast reaches everyone else.
        """
        client_id = uuid4().hex[:12]
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._connections.setdefault(workspace, {})[client_id] = {
            "queue": queue,
            "kind": kind,
            "label": label,
            "connected_at": self._clock(),
        }
        self._broadcast(workspace, exclude=client_id)
        return client_id, queue

    def disconnect(self, workspace: str, client_id: str) -> None:
        conns = self._connections.get(workspace)
        if not conns or client_id not in conns:
            return
        del conns[client_id]
        if not conns:
            del self._connections[workspace]
        self._broadcast(workspace)

    # -- write-derived presence ------------------------------------------- #
    def note_event(self, event: DomainEvent) -> None:
        """Count a recent agent write as presence (rolling ``write_ttl``).

        Only ``agent`` actors register: humans announce themselves via SSE
        and ``system`` cascades are not a party someone can talk to.
        """
        actor = event.actor
        if actor is None or actor.kind != "agent":
            return
        workspace = event.workspace_id
        key = (actor.kind, actor.id or "", actor.label or "")
        now = self._clock()
        writers = self._writers.setdefault(workspace, {})
        entry = writers.get(key)
        fresh = entry is not None and now - entry["last_write_at"] <= self._write_ttl
        if fresh:
            entry["last_write_at"] = now
        else:
            # New writer, or one whose window lapsed: (re)join the roster.
            writers[key] = {
                "kind": actor.kind,
                "id": actor.id,
                "label": actor.label,
                "connected_at": now,
                "last_write_at": now,
            }
            self._broadcast(workspace)
        self._schedule_sweep(workspace)

    def sweep(self, workspace: str) -> None:
        """Drop expired write-derived entries; broadcast if any left the roster."""
        self._sweep_handles.pop(workspace, None)
        writers = self._writers.get(workspace)
        if not writers:
            return
        now = self._clock()
        expired = [
            key for key, e in writers.items() if now - e["last_write_at"] > self._write_ttl
        ]
        for key in expired:
            del writers[key]
        if not writers:
            del self._writers[workspace]
        if expired:
            self._broadcast(workspace)
        if workspace in self._writers:
            self._schedule_sweep(workspace)

    def _schedule_sweep(self, workspace: str) -> None:
        """Arm one timer per workspace to expire the earliest writer.

        A pending timer is enough: firing early is a harmless no-op sweep
        that re-arms itself while writers remain. Outside a running loop
        (unit tests driving the tracker directly) expiry stays lazy —
        ``roster``/``sweep`` filter by the injected clock.
        """
        if workspace in self._sweep_handles:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        writers = self._writers.get(workspace)
        if not writers:
            return
        earliest = min(e["last_write_at"] for e in writers.values())
        delay = max(0.0, earliest + self._write_ttl - self._clock()) + 0.1
        self._sweep_handles[workspace] = loop.call_later(delay, self.sweep, workspace)

    # -- roster ------------------------------------------------------------ #
    def roster(self, workspace: str) -> list[dict[str, Any]]:
        """The current roster: SSE connections + unexpired recent writers."""
        now = self._clock()
        entries: list[dict[str, Any]] = [
            {
                "client_id": client_id,
                "kind": conn["kind"],
                "label": conn["label"],
                "connected_at": conn["connected_at"],
                "via": "sse",
            }
            for client_id, conn in self._connections.get(workspace, {}).items()
        ]
        entries.extend(
            {
                "kind": e["kind"],
                "id": e["id"],
                "label": e["label"],
                "connected_at": e["connected_at"],
                "last_write_at": e["last_write_at"],
                "via": "writes",
            }
            for e in self._writers.get(workspace, {}).values()
            if now - e["last_write_at"] <= self._write_ttl
        )
        entries.sort(key=lambda e: e["connected_at"])
        return entries

    def payload(self, workspace: str) -> dict[str, Any]:
        """The wire shape of one ``presence`` event / HTTP response body."""
        return {"workspace": workspace, "present": self.roster(workspace)}

    def _broadcast(self, workspace: str, *, exclude: str | None = None) -> None:
        conns = self._connections.get(workspace)
        if not conns:
            return
        payload = self.payload(workspace)
        for client_id, conn in conns.items():
            if client_id == exclude:
                continue
            conn["queue"].put_nowait(payload)

    def close(self) -> None:
        for handle in self._sweep_handles.values():
            handle.cancel()
        self._sweep_handles.clear()
        self._connections.clear()
        self._writers.clear()


def fetch_presence(data_dir: Path, slug: str, *, timeout: float = 3.0) -> dict[str, Any]:
    """Roster for ``slug`` from the running ``anchor serve`` bound to ``data_dir``.

    Presence lives in the serve process's memory, so MCP/CLI (separate
    processes) read it over HTTP. With no serve bound to the project the
    roster is empty by construction — nobody can be watching a UI that
    isn't up — and the result says so in ``note`` instead of erroring.
    """
    from anchor.infra.serve_registry import find_serve_for_data_dir

    record = find_serve_for_data_dir(data_dir)
    if record is None:
        return {
            "workspace": slug,
            "present": [],
            "serve": None,
            "note": (
                "no running `anchor serve` is bound to this project; presence "
                "is tracked by the serve process, so nobody is watching a UI."
            ),
        }
    base_url = record.base_url()
    url = f"{base_url}/api/workspaces/{quote(slug, safe='')}/presence"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as rsp:  # noqa: S310 - loopback serve from local registry
            data = json.loads(rsp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "workspace": slug,
                "present": [],
                "serve": base_url,
                "error": f"workspace {slug!r} not found on {base_url}",
            }
        return {
            "workspace": slug,
            "present": [],
            "serve": base_url,
            "error": f"presence fetch failed: HTTP {exc.code}",
        }
    except (OSError, ValueError) as exc:
        return {
            "workspace": slug,
            "present": [],
            "serve": base_url,
            "error": f"presence fetch failed: {exc}",
        }
    data.setdefault("serve", base_url)
    return data
