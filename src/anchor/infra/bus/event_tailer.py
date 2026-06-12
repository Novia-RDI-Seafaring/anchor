"""Cross-process event bridge.

The in-process EventBus only carries events written by the *current*
Python process. When another adapter (CLI in a separate shell, MCP-stdio
subprocess, ...) appends to `events.jsonl`, the HTTP server's SSE
subscribers never see it without help.

`EventTailer` watches a workspace's `events.jsonl`, parses new lines, and
republishes them onto the in-process bus. Client SSE subscribers already
filter by version (`state.version >= evt.version`), so a same-process event
being seen twice (once via direct publish, once via the tailer) is a no-op on
the client side.

The tailer normally seeks to end-of-file on start so historical events are
not replayed. The SSE route can instead pass the snapshot version it just
sent to the browser; the tailer then starts just after the last event at or
below that version. This closes the race where a CLI/MCP write lands after
the snapshot was read but before the tailer reached EOF.

`TailerRegistry.ensure(slug)` is called lazily by the SSE router so we
only tail workspaces that actually have live subscribers.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from anchor.core.events.envelope import DomainEvent
from anchor.core.ports.event_bus import EventBus


class EventTailer:
    def __init__(self, *, slug: str, events_path: Path, bus: EventBus, poll_interval: float = 0.2) -> None:
        self.slug = slug
        self.events_path = events_path
        self.bus = bus
        self.poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._offset = 0
        self._stop = asyncio.Event()

    def start(self, *, replay_after_version: int | None = None) -> None:
        if self._task and not self._task.done():
            return
        self._offset = self._initial_offset(replay_after_version)
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"event-tailer:{self.slug}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None

    async def _run(self) -> None:
        partial = b""
        while not self._stop.is_set():
            try:
                if self.events_path.exists():
                    size = self.events_path.stat().st_size
                    if size > self._offset:
                        with self.events_path.open("rb") as f:
                            f.seek(self._offset)
                            chunk = f.read(size - self._offset)
                        self._offset = size
                        partial += chunk
                        while b"\n" in partial:
                            line, partial = partial.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            await self._publish(line)
                    elif size < self._offset:
                        # File truncated/rewritten. Reset.
                        self._offset = size
                        partial = b""
            except FileNotFoundError:
                # The event file may not exist until the first workspace event.
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                # Timeout is the polling cadence; loop again unless stopped.
                pass

    async def _publish(self, line: bytes) -> None:
        try:
            rec = json.loads(line.decode())
            event = DomainEvent(**rec)
        except (ValueError, TypeError):
            return
        await self.bus.publish(event)

    def _initial_offset(self, replay_after_version: int | None) -> int:
        if not self.events_path.exists():
            return 0
        if replay_after_version is None:
            return self.events_path.stat().st_size

        offset = 0
        try:
            with self.events_path.open("rb") as f:
                while True:
                    line = f.readline()
                    if not line:
                        return offset
                    next_offset = f.tell()
                    try:
                        rec = json.loads(line.decode())
                        version = int(rec.get("version", 0))
                    except (ValueError, TypeError):
                        offset = next_offset
                        continue
                    if version <= replay_after_version:
                        offset = next_offset
                        continue
                    return offset
        except FileNotFoundError:
            return 0


class TailerRegistry:
    """Holds one EventTailer per active workspace."""

    def __init__(self, *, canvases_root: Path, bus: EventBus) -> None:
        self.canvases_root = Path(canvases_root)
        self.bus = bus
        self._tailers: dict[str, EventTailer] = {}
        self._lock = asyncio.Lock()

    async def ensure(self, slug: str, *, replay_after_version: int | None = None) -> None:
        async with self._lock:
            t = self._tailers.get(slug)
            if t is None:
                events_path = self.canvases_root / slug / "events.jsonl"
                t = EventTailer(slug=slug, events_path=events_path, bus=self.bus)
                self._tailers[slug] = t
            t.start(replay_after_version=replay_after_version)

    async def close(self) -> None:
        async with self._lock:
            tailers = list(self._tailers.values())
            self._tailers.clear()
        await asyncio.gather(*(t.stop() for t in tailers), return_exceptions=True)
