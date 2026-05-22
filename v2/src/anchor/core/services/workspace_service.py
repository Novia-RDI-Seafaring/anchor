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
from anchor.core.workspace.align import (
    Anchor,
    Axis,
    SelectedNode,
    align_nodes as _align_nodes_pure,
    distribute_nodes as _distribute_nodes_pure,
)
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
        """Return the meta of every workspace plus per-canvas counts + ref graph.

        The envelope each entry carries beyond ``WorkspaceMeta``:

          - ``node_count`` / ``edge_count`` — current snapshot sizes.
          - ``references`` — slugs this canvas's ``node_type == "canvas"``
            nodes point at via ``data.canvas_slug``. Self-links and unset
            targets are filtered.
          - ``referenced_by`` — reverse map. Built in a second pass after
            every canvas's outgoing refs are collected. A canvas with an
            empty ``referenced_by`` is a tree root (or part of a cycle
            with no outside parent).

        The frontend's landing page renders this as a folder tree; the
        MCP `canvas_list_workspaces` tool and the `anchor canvas list` CLI
        return the same envelope. The store is loaded once per slug —
        cheap for the in-memory store, a state.json read for the fs store.
        Cycles are tolerated: A → B → A round-trips through both
        ``references`` and ``referenced_by`` and the UI shows a "↩ cycle"
        marker rather than recursing forever.
        """
        metas = await self.store.list_workspaces()
        out: list[dict[str, Any]] = []
        # Pass 1: collect outgoing references per slug.
        for m in metas:
            try:
                ws = await self.store.load(m.slug)
            except Exception:
                # A meta whose state can't be loaded shouldn't crash the
                # whole list — surface zero counts and skip the ref scan.
                d = m.model_dump()
                d.update(node_count=0, edge_count=0, references=[], referenced_by=[])
                out.append(d)
                continue
            refs: list[str] = []
            seen_refs: set[str] = set()
            for n in ws.nodes.values():
                if n.node_type != "canvas":
                    continue
                target = (n.data or {}).get("canvas_slug")
                if not isinstance(target, str) or not target:
                    continue
                if target == m.slug:
                    continue  # self-link is meaningless
                if target in seen_refs:
                    continue
                seen_refs.add(target)
                refs.append(target)
            d = m.model_dump()
            d.update(
                node_count=len(ws.nodes),
                edge_count=len(ws.edges),
                references=refs,
                referenced_by=[],  # filled in pass 2
            )
            out.append(d)
        # Pass 2: invert into referenced_by. Index by slug so we don't
        # quadratic-scan when graphs grow.
        index: dict[str, dict[str, Any]] = {e["slug"]: e for e in out}
        for entry in out:
            for target in entry["references"]:
                bucket = index.get(target)
                if bucket is None:
                    continue
                if entry["slug"] in bucket["referenced_by"]:
                    continue
                bucket["referenced_by"].append(entry["slug"])
        return out

    async def create_workspace(self, slug: str, title: str = "") -> dict[str, Any]:
        meta = await self.store.create(slug, title=title)
        return meta.model_dump()

    async def get_state(self, slug: str) -> dict[str, Any]:
        ws = await self.store.load(slug)
        return ws.get_state()

    async def list_placeholders(self, slug: str) -> list[dict[str, Any]]:
        """Return every node on ``slug`` flagged ``data.placeholder == true``.

        Placeholders are the agent-visible "fill these in" affordance. The
        web UI renders them with a dashed sky-blue outline + hint chip; this
        method is what the agent calls to find them. Same envelope is
        exposed via HTTP ``GET /api/workspaces/{slug}/placeholders``, the
        ``canvas_list_placeholders`` MCP tool, and ``anchor canvas
        placeholders <slug>`` (per the v2 adapter-parity rule).

        Each entry: ``{id, node_type, label, hint, x, y, data}`` where
        ``hint`` is the optional ``data.placeholder_hint`` (or empty string).
        """
        ws = await self.store.load(slug)
        out: list[dict[str, Any]] = []
        for n in ws.nodes.values():
            data = n.data or {}
            if data.get("placeholder") is not True:
                continue
            hint = data.get("placeholder_hint")
            out.append({
                "id": n.id,
                "node_type": n.node_type,
                "label": n.label,
                "hint": hint if isinstance(hint, str) else "",
                "x": n.x,
                "y": n.y,
                "data": dict(data),
            })
        return out

    async def add_node(self, slug: str, **kwargs: Any) -> tuple[Workspace, DomainEvent]:
        cmd = NodeAdded(id=kwargs.pop("id", None) or new_id(), **kwargs)
        return await self._dispatch(slug, cmd)

    async def create_sub_canvas(
        self,
        parent_slug: str,
        sub_slug: str,
        *,
        title: str = "",
        x: float = 0.0,
        y: float = 0.0,
    ) -> dict[str, Any]:
        """Create a child workspace and drop a linking ``canvas`` node onto the parent.

        Composite over ``create_workspace`` + ``add_node`` so agents and UI
        can drill in with a single call. Both steps run under the parent's
        lock so the linking node is guaranteed to reference an extant
        child workspace by the time the ``NodeAdded`` event lands on the bus.

        The linking node carries ``data.canvas_slug`` (the link target) and
        ``data.title`` (display name). The UI's ``SubCanvasPrimitive``
        reads both and double-click navigates to ``/c/<canvas_slug>``.
        """
        if not sub_slug or sub_slug == parent_slug:
            raise CommandError(
                "sub-canvas slug must be non-empty and different from parent "
                f"({parent_slug!r})",
            )
        async with self.locks.lock(parent_slug):
            # Touch the parent first so a 404 surfaces before we provision a child.
            await self.store.load(parent_slug)
            child_meta = await self.store.create(sub_slug, title=title or sub_slug)
            cmd = NodeAdded(
                id=new_id(),
                node_type="canvas",
                label=title or sub_slug,
                x=x,
                y=y,
                data={"canvas_slug": sub_slug, "title": title or sub_slug},
            )
            state = await self.store.load(parent_slug)
            validate_command(state, cmd, node_types=self.node_types)
            env = self._envelope(parent_slug, cmd)
            version = await self.store.append_event(parent_slug, env)
            env.version = version
            new_state = apply(state, cmd)
            new_state.version = version
            new_state.last_event_id = env.id
            await self.store.snapshot(parent_slug, new_state)
            await self.bus.publish(env)
            return {
                "child": child_meta.model_dump(),
                "node": {
                    "id": cmd.id,
                    "node_type": cmd.node_type,
                    "label": cmd.label,
                    "x": cmd.x,
                    "y": cmd.y,
                    "data": cmd.data,
                },
                "event": env.model_dump(),
                "state": new_state.get_state(),
            }

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
        direction: Literal["outgoing", "incoming", "any"] = "any",
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Re-lay-out the subtree rooted at ``root_id`` in one atomic block.

        Walks the edge graph from the root, computes a tidy position per
        descendant, and emits one ``NodeMoved`` per node whose position
        actually changes. The root itself never moves. Cycles are allowed
        but each node is visited at most once.

        ``direction`` controls how the BFS walks edges (see
        ``anchor.core.workspace.layout``):

          - ``"outgoing"`` — only follow ``edge.source == current`` (parent → child).
          - ``"incoming"`` — only follow ``edge.target == current`` (reports-to).
          - ``"any"`` (default) — undirected projection, the v1 behaviour.

        Default ``"any"`` keeps existing callers / UI flows working; the
        UI / CLI / MCP / HTTP adapters all pass through whatever the user
        picked. The user-visible bug this fixes is that an undirected walk
        from a mid-tree node (e.g. ``CFO`` on the ``acme-org`` canvas) drags
        the parent in too; picking ``"incoming"`` gives strict-descendant
        scoping for the reports-to convention.

        Even though the public knob is called ``algo="dagre"``, the layout
        math is a hand-rolled Python tree placement — we deliberately do
        not pull in a JS or Python dagre dependency. The "dagre" label is
        kept on the API because that's what the UI ships and what the user
        thinks of when they say "tree-organize this".

        Raises ``CommandError`` if the root node does not exist. Returns an
        empty event list (and the unchanged workspace) when the root has no
        descendants in the chosen ``direction`` — there's nothing to move."""
        if algo != "dagre":
            raise ValueError(
                f"unsupported organize algo: {algo!r} (only 'dagre' is shipped)",
            )
        if orientation not in {"vertical", "horizontal"}:
            raise ValueError(
                f"unsupported orientation: {orientation!r} "
                "(use 'vertical' or 'horizontal')",
            )
        if direction not in {"outgoing", "incoming", "any"}:
            raise ValueError(
                f"unsupported direction: {direction!r} "
                "(use 'outgoing', 'incoming', or 'any')",
            )

        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            if root_id not in state.nodes:
                raise CommandError(f"node {root_id!r} does not exist")

            node_likes = [NodeLike(id=n.id, x=n.x, y=n.y) for n in state.nodes.values()]
            edge_likes = [EdgeLike(source=e.source, target=e.target) for e in state.edges.values()]
            placements = organize_subtree(
                node_likes, edge_likes, root_id,
                orientation=orientation, direction=direction,
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

    async def align_nodes(
        self,
        slug: str,
        ids: list[str],
        anchor: Anchor,
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Align the listed nodes' positions to a shared edge or midline.

        Emits one ``NodeMoved`` per node that actually moves, all sharing a
        single ``causation_id`` so the SSE consumer can group the burst as a
        single logical "align" operation. Raises ``CommandError`` for unknown
        ids; raises ``ValueError`` for an unsupported anchor value (the pure
        math owns that error)."""
        return await self._geom_op(
            slug, ids,
            lambda items: _align_nodes_pure(items, anchor),
            op_label=f"align {anchor!r}",
            min_count=2,
        )

    async def distribute_nodes(
        self,
        slug: str,
        ids: list[str],
        axis: Axis,
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Distribute centres of the listed nodes evenly along ``axis``.

        End nodes stay anchored; the in-between centres get equally-spaced
        slots. Requires at least three nodes (the pure math returns no moves
        for fewer)."""
        return await self._geom_op(
            slug, ids,
            lambda items: _distribute_nodes_pure(items, axis),
            op_label=f"distribute {axis!r}",
            min_count=3,
        )

    async def _geom_op(
        self,
        slug: str,
        ids: list[str],
        compute: "callable[[list[SelectedNode]], dict[str, tuple[float, float]]]",  # noqa: F821
        *,
        op_label: str,
        min_count: int,
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Shared engine for align / distribute.

        Loads state, looks each id up, asks the pure-math callable for new
        positions, then emits one NodeMoved per genuine change inside a
        single causation envelope. Keeps both ops on the exact same code
        path as ``organize_subtree`` — appended events go through the same
        validate → append → publish dance."""
        if len(ids) < min_count:
            raise CommandError(
                f"{op_label} needs at least {min_count} nodes; got {len(ids)}",
            )
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            missing = [nid for nid in ids if nid not in state.nodes]
            if missing:
                raise CommandError(
                    f"{op_label}: nodes do not exist: {sorted(missing)!r}",
                )

            selected = [
                SelectedNode(
                    id=nid,
                    x=state.nodes[nid].x,
                    y=state.nodes[nid].y,
                    width=state.nodes[nid].width,
                    height=state.nodes[nid].height,
                )
                for nid in ids
            ]
            placements = compute(selected)
            if not placements:
                return state, []

            envelopes: list[DomainEvent] = []
            new_state = state
            cause = new_event_id()
            for nid, (nx, ny) in placements.items():
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
