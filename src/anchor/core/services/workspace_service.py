"""WorkspaceService orchestrates commands against a workspace.

Pure orchestration: takes ports as constructor args, validates commands
against current state, applies events, persists, and publishes.
"""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Literal

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
from anchor.core.services.workspace_geometry import WorkspaceGeometryOperations
from anchor.core.services.workspace_operation_support import WorkspaceLocks
from anchor.core.services.workspace_references import WorkspaceReferenceOperations
from anchor.core.workspace.align import Anchor, Axis
from anchor.core.workspace.builtin_node_types import builtin_node_type_registry
from anchor.core.workspace.layout import NodeLike, find_free_position
from anchor.core.workspace.node_types import NodeTypeRegistry
from anchor.core.workspace.reducer import apply, cascade_events_for_remove
from anchor.core.workspace.workspace import CommandError, Workspace, validate_command


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
        locks: WorkspaceLocks | None = None,
        node_types: NodeTypeRegistry | None = None,
        snapshotter: SnapshotPort | None = None,
    ) -> None:
        self.store = store
        self.bus = bus
        self.clock: Clock = clock or SystemClock()
        self.locks: WorkspaceLocks = locks or _NoLocks()
        # Default to the built-in shape/card contract so every adapter gets
        # the #191 unknown-data-key warning + queryable node-types schema
        # without each builder wiring it. The built-in types carry no
        # data_schema, so this never blocks a write; it only documents and
        # warns. Pass node_types=EMPTY_REGISTRY explicitly to opt out.
        self.node_types = (
            node_types if node_types is not None else builtin_node_type_registry()
        )
        self.snapshotter = snapshotter
        self._references = WorkspaceReferenceOperations(
            self.store,
            self.locks,
            self.clock,
            self._dispatch_locked,
        )
        self._geometry = WorkspaceGeometryOperations(
            self.store,
            self.bus,
            self.locks,
            self.clock,
        )

    async def list_workspaces(self) -> list[dict[str, Any]]:
        """Return the meta of every workspace plus per-canvas counts + ref graph.

        The envelope each entry carries beyond ``WorkspaceMeta``:

          - ``node_count`` / ``edge_count``: current snapshot sizes.
          - ``references``: slugs this canvas's ``node_type == "canvas"``
            nodes point at via ``data.canvas_slug``. Self-links and unset
            targets are filtered.
          - ``referenced_by``: reverse map. Built in a second pass after
            every canvas's outgoing refs are collected. A canvas with an
            empty ``referenced_by`` is a tree root (or part of a cycle
            with no outside parent).

        The frontend's landing page renders this as a folder tree; the
        MCP `canvas_list_workspaces` tool and the `anchor canvas list` CLI
        return the same envelope. The store is loaded once per slug,
        cheap for the in-memory store, a state.json read for the fs store.
        Cycles are tolerated: A -> B -> A round-trips through both
        ``references`` and ``referenced_by`` and the UI shows a cycle
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
                # whole list. Surface zero counts and skip the reference scan.
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

    async def delete_workspace(self, slug: str) -> dict[str, Any]:
        async with self.locks.lock(slug):
            await self.store.delete(slug)
        return {"slug": slug, "deleted": True}

    async def rename_workspace(self, slug: str, *, title: str) -> dict[str, Any]:
        """Update the workspace's display title in meta + state. Slug is
        immutable. Idempotent."""
        meta = await self.store.rename(slug, title=title)
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

    async def add_node(
        self, slug: str, *, place: str | None = None, **kwargs: Any,
    ) -> tuple[Workspace, DomainEvent]:
        """Add a node. Resolves a non-overlapping position server-side when no
        coordinates are supplied (or ``place="auto"``), returning the resolved
        (x, y) on the emitted event so the caller can track layout (#189).

        Auto-place triggers when ``place == "auto"`` OR neither ``x`` nor ``y``
        was given. When explicit coordinates ARE given (and ``place`` is not
        "auto") the node lands exactly there, as before. The resolved
        position is always readable from ``event.payload["x"/"y"]``."""
        if place not in (None, "auto", "exact"):
            raise CommandError(
                f"unknown place mode: {place!r} (use 'auto' or 'exact')",
            )
        node_id = kwargs.pop("id", None) or new_id()
        gave_coords = ("x" in kwargs) or ("y" in kwargs)
        auto = place == "auto" or (place is None and not gave_coords)
        async with self.locks.lock(slug):
            if auto:
                state = await self.store.load(slug)
                existing = [
                    NodeLike(id=n.id, x=n.x, y=n.y, width=n.width, height=n.height)
                    for n in state.nodes.values()
                ]
                x, y = find_free_position(
                    existing,
                    width=kwargs.get("width"),
                    height=kwargs.get("height"),
                )
                kwargs["x"] = x
                kwargs["y"] = y
            cmd = NodeAdded(id=node_id, **kwargs)
            return await self._dispatch_locked(slug, cmd)

    def node_types_schema(self, name: str | None = None) -> list[dict[str, Any]]:
        """Return the per-node-type data-field contract (#191).

        Empty list when no registry is wired. Each entry:
        ``{name, description, data_fields, body_field}``. Surfaced verbatim
        by the ``node-types`` CLI command, the HTTP route, and the MCP tool."""
        if self.node_types is None:
            return []
        return self.node_types.schema(name)

    def unknown_data_keys(self, node_type: str, data: dict[str, Any] | None) -> list[str]:
        """Data keys a node type's renderer will ignore (#191).

        Empty when no registry is wired, the type is open, or every key is
        recognised. Adapters attach a non-blocking warning when non-empty so a
        write never silently drops a dead field."""
        if self.node_types is None or not data:
            return []
        return self.node_types.unknown_data_keys(node_type, data)

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

    async def create_reference(
        self,
        slug: str,
        *,
        source_ref: dict[str, Any],
        label: str | None = None,
        created_by: str = "human",
    ) -> dict[str, Any]:
        """Author a reference and append it to the canvas bibliography."""
        return await self._references.create(
            slug,
            source_ref=source_ref,
            label=label,
            created_by=created_by,
        )

    async def list_references(self, slug: str) -> list[dict[str, Any]]:
        """Return the canvas bibliography."""
        return await self._references.list(slug)

    async def attach_reference(
        self,
        slug: str,
        reference_id: str,
        *,
        node_id: str,
        row_index: int | None = None,
    ) -> tuple[Workspace, DomainEvent]:
        """Attach a stored reference to a node or spec row."""
        return await self._references.attach(
            slug,
            reference_id,
            node_id=node_id,
            row_index=row_index,
        )

    async def remove_reference(
        self,
        slug: str,
        reference_id: str,
    ) -> tuple[Workspace, DomainEvent]:
        """Remove a reference from the canvas bibliography."""
        return await self._references.remove(slug, reference_id)

    async def update_reference(
        self,
        slug: str,
        reference_id: str,
        *,
        label: str | None = None,
    ) -> tuple[Workspace, DomainEvent]:
        """Edit a reference's human caption."""
        return await self._references.update(slug, reference_id, label=label)

    async def organize_subtree(
        self,
        slug: str,
        root_id: str,
        *,
        orientation: Literal["vertical", "horizontal"] = "vertical",
        algo: Literal["dagre"] = "dagre",
        direction: Literal["outgoing", "incoming", "any"] = "any",
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Lay out descendants of ``root_id`` and emit grouped move events."""
        return await self._geometry.organize_subtree(
            slug,
            root_id,
            orientation=orientation,
            algo=algo,
            direction=direction,
        )

    async def align_nodes(
        self,
        slug: str,
        ids: list[str],
        anchor: Anchor,
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Align nodes to a shared edge or midline."""
        return await self._geometry.align_nodes(slug, ids, anchor)

    async def distribute_nodes(
        self,
        slug: str,
        ids: list[str],
        axis: Axis,
    ) -> tuple[Workspace, list[DomainEvent]]:
        """Distribute node centers evenly along ``axis``."""
        return await self._geometry.distribute_nodes(slug, ids, axis)

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
        the port. Core never imports Playwright itself.
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
            return await self._dispatch_locked(slug, cmd)

    async def _dispatch_locked(self, slug: str, cmd: BaseModel) -> tuple[Workspace, DomainEvent]:
        """Dispatch body assuming the caller already holds the workspace lock.

        Split out so ``add_node`` can read state (for auto-placement) and
        write the resulting command inside one lock acquisition. The
        re-entrant lock impls don't all support nesting."""
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
