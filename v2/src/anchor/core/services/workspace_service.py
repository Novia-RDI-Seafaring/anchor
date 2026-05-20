"""WorkspaceService — orchestrates commands against a workspace.

Pure orchestration: takes ports as constructor args, validates commands
against current state, applies events, persists, and publishes.
"""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from anchor.core.clock import Clock, SystemClock
from anchor.core.events.canvas import (
    CanvasCleared,
    EdgeAdded,
    EdgeRemoved,
    EdgeUpdated,
    NodeAdded,
    NodeMoved,
    NodeRemoved,
    NodeReparented,
    NodeResized,
    NodeUpdated,
)
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id, new_id
from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.snapshot import SnapshotPort, SnapshotResult
from anchor.core.ports.workspace_store import WorkspaceStore
from anchor.core.workspace.layout import EdgeLike, NodeLike, organize_subtree
from anchor.core.workspace.node_types import NodeTypeRegistry
from anchor.core.workspace.reducer import apply, cascade_events_for_remove
from anchor.core.workspace.workspace import CommandError, Workspace, validate_command


class _LocksProto(Protocol):
    def lock(self, workspace_id: str) -> AbstractAsyncContextManager[None]: ...


@asynccontextmanager
async def _no_lock():
    yield None


class _NoLocks:
    def lock(self, workspace_id: str) -> AbstractAsyncContextManager[None]:
        del workspace_id
        return _no_lock()


class WorkspaceService:
    def __init__(
        self,
        store: WorkspaceStore,
        bus: EventBus,
        *,
        clock: Clock | None = None,
        locks: _LocksProto | None = None,
        node_types: NodeTypeRegistry | None = None,
        snapshotter: SnapshotPort | None = None,
    ) -> None:
        self.store = store
        self.bus = bus
        self.clock: Clock = clock or SystemClock()
        self.locks: _LocksProto = locks or _NoLocks()
        self.node_types = node_types
        self.snapshotter = snapshotter

    async def list_workspaces(self) -> list[dict[str, Any]]:
        return [m.model_dump() for m in await self.store.list_workspaces()]

    async def create_workspace(self, slug: str, title: str = "") -> dict[str, Any]:
        meta = await self.store.create(slug, title=title)
        return meta.model_dump()

    async def get_state(self, slug: str) -> dict[str, Any]:
        ws = await self.store.load(slug)
        return ws.get_state()

    async def add_node(self, slug: str, **kwargs: Any) -> tuple[Workspace, DomainEvent]:
        cmd = NodeAdded(id=kwargs.pop("id", None) or new_id(), **kwargs)
        return await self._dispatch(slug, cmd)

    async def remove_node(self, slug: str, node_id: str) -> tuple[Workspace, list[DomainEvent]]:
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            cmd = NodeRemoved(id=node_id)
            validate_command(state, cmd, node_types=self.node_types)
            cascade = cascade_events_for_remove(state, node_id)
            envelopes: list[DomainEvent] = []
            new_state = state
            cause = new_event_id()
            for ev in [*cascade, cmd]:
                env = self._envelope(slug, ev, causation_id=cause)
                version = await self.store.append_event(slug, env)
                env.version = version
                new_state = apply(new_state, ev)
                new_state.version = version
                new_state.last_event_id = env.id
                envelopes.append(env)
            await self.store.snapshot(slug, new_state)
            for env in envelopes:
                await self.bus.publish(env)
            return new_state, envelopes

    async def move_node(self, slug: str, node_id: str, x: float, y: float) -> tuple[Workspace, DomainEvent]:
        return await self._dispatch(slug, NodeMoved(id=node_id, x=x, y=y))

    async def resize_node(self, slug: str, node_id: str, width: float, height: float) -> tuple[Workspace, DomainEvent]:
        return await self._dispatch(slug, NodeResized(id=node_id, width=width, height=height))

    async def update_node(self, slug: str, node_id: str, fields: dict[str, Any]) -> tuple[Workspace, DomainEvent]:
        return await self._dispatch(slug, NodeUpdated(id=node_id, fields=dict(fields)))

    async def reparent_node(self, slug: str, node_id: str, parent: str | None) -> tuple[Workspace, DomainEvent]:
        return await self._dispatch(slug, NodeReparented(id=node_id, parent=parent))

    async def add_edge(self, slug: str, **kwargs: Any) -> tuple[Workspace, DomainEvent]:
        cmd = EdgeAdded(id=kwargs.pop("id", None) or new_id(), **kwargs)
        return await self._dispatch(slug, cmd)

    async def remove_edge(self, slug: str, edge_id: str) -> tuple[Workspace, DomainEvent]:
        return await self._dispatch(slug, EdgeRemoved(id=edge_id))

    async def update_edge(self, slug: str, edge_id: str, fields: dict[str, Any]) -> tuple[Workspace, DomainEvent]:
        return await self._dispatch(slug, EdgeUpdated(id=edge_id, fields=dict(fields)))

    async def clear(self, slug: str) -> tuple[Workspace, DomainEvent]:
        return await self._dispatch(slug, CanvasCleared())

    async def organize_subtree(
        self,
        slug: str,
        root_id: str,
        *,
        orientation: Literal["vertical", "horizontal"] = "vertical",
        algo: Literal["dagre"] = "dagre",
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Re-lay-out the subtree rooted at ``root_id`` in one atomic block.

        Walks the (undirected) edge graph from the root, computes a tidy
        position per descendant, and emits one ``NodeMoved`` per node whose
        position actually changes. The root itself never moves. Cycles are
        allowed but each node is visited at most once.

        Even though the public knob is called ``algo="dagre"``, the layout
        math is a hand-rolled Python tree placement (see
        ``anchor.core.workspace.layout``) — we deliberately do not pull in
        a JS or Python dagre dependency. The "dagre" label is kept on the
        API because that's what the UI ships and what the user thinks of
        when they say "tree-organize this".

        Raises ``CommandError`` if the root node does not exist. Returns an
        empty event list (and the unchanged workspace) when the root has no
        descendants — there's nothing to move."""
        if algo != "dagre":
            raise ValueError(
                f"unsupported organize algo: {algo!r} (only 'dagre' is shipped)",
            )
        if orientation not in {"vertical", "horizontal"}:
            raise ValueError(
                f"unsupported orientation: {orientation!r} "
                "(use 'vertical' or 'horizontal')",
            )

        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            if root_id not in state.nodes:
                raise CommandError(f"node {root_id!r} does not exist")

            node_likes = [NodeLike(id=n.id, x=n.x, y=n.y) for n in state.nodes.values()]
            edge_likes = [EdgeLike(source=e.source, target=e.target) for e in state.edges.values()]
            placements = organize_subtree(
                node_likes, edge_likes, root_id, orientation=orientation,
            )

            # Filter: only emit a move if the position actually shifts.
            # Saves a flurry of no-op SSE events when the user re-organizes
            # an already-tidy tree.
            moves: list[tuple[str, float, float]] = []
            for nid, (nx, ny) in placements.items():
                n = state.nodes.get(nid)
                if n is None:
                    continue
                if n.x == nx and n.y == ny:
                    continue
                moves.append((nid, nx, ny))

            if not moves:
                return state, []

            envelopes: list[DomainEvent] = []
            new_state = state
            cause = new_event_id()
            for nid, nx, ny in moves:
                ev = NodeMoved(id=nid, x=nx, y=ny)
                env = self._envelope(slug, ev, causation_id=cause)
                version = await self.store.append_event(slug, env)
                env.version = version
                new_state = apply(new_state, ev)
                new_state.version = version
                new_state.last_event_id = env.id
                envelopes.append(env)
            await self.store.snapshot(slug, new_state)
            for env in envelopes:
                await self.bus.publish(env)
            return new_state, envelopes

    async def snapshot(
        self,
        slug: str,
        *,
        format: str = "png",
        viewport: tuple[int, int] | None = None,
        full_page: bool = True,
    ) -> SnapshotResult:
        """Render the workspace canvas to an image via the wired SnapshotPort.

        Service-level guard: verifies the workspace exists (raising
        `CommandError` / `KeyError` early if not) so the snapshotter doesn't
        burn a Chromium navigation on a 404. Then delegates rendering to
        the port — core never imports playwright itself.
        """
        if self.snapshotter is None:
            raise RuntimeError(
                "WorkspaceService.snapshot called but no snapshotter was wired. "
                "Pass snapshotter=... to the constructor (see "
                "anchor.infra.snapshot.headless_chromium_snapshotter).",
            )
        # Touch the store to surface 404s as the same error type other
        # ops raise. This is cheap (snapshot read).
        await self.store.load(slug)
        if format not in {"png", "svg"}:
            raise ValueError(f"unsupported snapshot format: {format!r} (use 'png' or 'svg')")
        return await self.snapshotter.snapshot(
            slug, format=format, viewport=viewport, full_page=full_page,
        )

    async def _dispatch(self, slug: str, cmd: BaseModel) -> tuple[Workspace, DomainEvent]:
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            validate_command(state, cmd, node_types=self.node_types)
            env = self._envelope(slug, cmd)
            version = await self.store.append_event(slug, env)
            env.version = version
            new_state = apply(state, cmd)
            new_state.version = version
            new_state.last_event_id = env.id
            await self.store.snapshot(slug, new_state)
            await self.bus.publish(env)
            return new_state, env

    def _envelope(self, slug: str, evt: BaseModel, *, causation_id: str | None = None) -> DomainEvent:
        return DomainEvent(
            id=new_event_id(),
            ts=self.clock.now(),
            workspace_id=slug,
            type=getattr(evt, "type", evt.__class__.__name__),
            payload=evt.model_dump(),
            causation_id=causation_id,
        )
