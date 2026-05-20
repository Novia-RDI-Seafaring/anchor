"""Cross-process event bridge.

The in-process EventBus only carries events written by the *current*
Python process. When another adapter (CLI in a separate shell, MCP-stdio
subprocess, ...) appends to `events.jsonl`, the HTTP server's SSE
subscribers never see it without help.

`EventTailer` watches a workspace's `events.jsonl`, parses any new lines
appended after the tailer started, and republishes them onto the in-
process bus. Client SSE subscribers already filter by version
(`state.version >= evt.version`), so a same-process event being seen
twice (once via direct publish, once via the tailer) is a no-op on the
client side.

The tailer seeks to end-of-file on start so historical events are *not*
replayed — only writes appended after the tailer was registered are
republished.

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

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        if self.events_path.exists():
            self._offset = self.events_path.stat().st_size
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
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

    async def _publish(self, line: bytes) -> None:
        try:
            rec = json.loads(line.decode())
            event = DomainEvent(**rec)
        except (ValueError, TypeError):
            return
        await self.bus.publish(event)


class TailerRegistry:
    """Holds one EventTailer per active workspace."""

    def __init__(self, *, canvases_root: Path, bus: EventBus) -> None:
        self.canvases_root = Path(canvases_root)
        self.bus = bus
        self._tailers: dict[str, EventTailer] = {}
        self._lock = asyncio.Lock()

    async def ensure(self, slug: str) -> None:
        async with self._lock:
            t = self._tailers.get(slug)
            if t is None:
                events_path = self.canvases_root / slug / "events.jsonl"
                t = EventTailer(slug=slug, events_path=events_path, bus=self.bus)
                self._tailers[slug] = t
            t.start()

    async def close(self) -> None:
        async with self._lock:
            tailers = list(self._tailers.values())
            self._tailers.clear()
        await asyncio.gather(*(t.stop() for t in tailers), return_exceptions=True)
