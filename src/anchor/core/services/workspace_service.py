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
    ReferenceAttached,
    ReferenceCreated,
    ReferenceRemoved,
    ReferenceUpdated,
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
from anchor.core.workspace.layout import (
    EdgeLike,
    NodeLike,
    find_free_position,
    organize_subtree,
)
from anchor.core.workspace.builtin_node_types import builtin_node_type_registry
from anchor.core.workspace.node_types import NodeTypeRegistry
from anchor.core.workspace.reducer import apply, cascade_events_for_remove
from anchor.core.workspace.references import (
    Reference,
    ReferenceError,
    validate_source_ref,
)
from anchor.core.workspace.workspace import CommandError, Workspace, validate_command


class _LocksProto(Protocol):
    def lock(self, workspace_id: str) -> AbstractAsyncContextManager[None]:
        raise NotImplementedError


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
        # Default to the built-in shape/card contract so every adapter gets
        # the #191 unknown-data-key warning + queryable node-types schema
        # without each builder wiring it. The built-in types carry no
        # data_schema, so this never blocks a write — it only documents +
        # warns. Pass node_types=EMPTY_REGISTRY explicitly to opt out.
        self.node_types = (
            node_types if node_types is not None else builtin_node_type_registry()
        )
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

    # ── References (canvas-scoped bibliography, #147 slice 1) ───────────────
    #
    # Stored in ``Workspace.metadata['references']`` (a list). Canvas-scoped
    # for now; the maintainer decision is to keep this in canvas meta and
    # consider promoting to a project-level store later (cross-canvas reuse /
    # paper compilation). The op signatures are written so that promotion does
    # not change adapter callers.

    async def create_reference(
        self,
        slug: str,
        *,
        source_ref: dict[str, Any],
        label: str | None = None,
        created_by: str = "human",
    ) -> dict[str, Any]:
        """Author a reference and append it to the canvas bibliography.

        Validates the ``source_ref`` (slug + page required; bbox / region_id /
        detail optional), assigns a server-side id, stamps ``created_at`` from
        the injected clock (deterministic in tests), and emits a
        ``ReferenceCreated`` domain event so SSE clients update. Returns the
        stored reference dict (with its assigned id)."""
        try:
            sref = validate_source_ref(source_ref)
        except ReferenceError as e:
            raise CommandError(str(e)) from e
        if created_by not in ("human", "agent"):
            raise CommandError(
                f"created_by must be 'human' or 'agent', got {created_by!r}",
            )
        reference = Reference(
            id=new_id(),
            label=label,
            source_ref=sref,
            created_by=created_by,
            created_at=self.clock.now(),
        )
        ref_dict = reference.model_dump()
        async with self.locks.lock(slug):
            await self.store.load(slug)  # surface 404 before we append
            _, env = await self._dispatch_locked(
                slug, ReferenceCreated(reference=ref_dict),
            )
        del env  # event already published inside _dispatch_locked
        return ref_dict

    async def list_references(self, slug: str) -> list[dict[str, Any]]:
        """Return the canvas bibliography (``metadata['references']``).

        Empty list for a canvas that has never had a reference (backward
        compatible: no ``references`` key behaves exactly as today)."""
        ws = await self.store.load(slug)
        refs = ws.metadata.get("references")
        if not isinstance(refs, list):
            return []
        return [dict(r) for r in refs if isinstance(r, dict)]

    async def attach_reference(
        self,
        slug: str,
        reference_id: str,
        *,
        node_id: str,
        row_index: int | None = None,
    ) -> tuple[Workspace, DomainEvent]:
        """Attach a stored reference to a node (and optionally a spec row).

        Sets the target node/row's ``reference_id`` pointer + ``source_ref``
        (copied from the stored reference) so the fact resolves to its
        citation by id and drives the existing value-level highlight. Emits a
        ``ReferenceAttached`` domain event. Raises ``CommandError`` for an
        unknown reference id, unknown node, or out-of-range row."""
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            refs = state.metadata.get("references")
            ref = None
            if isinstance(refs, list):
                ref = next(
                    (r for r in refs if isinstance(r, dict) and r.get("id") == reference_id),
                    None,
                )
            if ref is None:
                raise CommandError(f"reference {reference_id!r} does not exist")
            cmd = ReferenceAttached(
                reference_id=reference_id,
                node_id=node_id,
                row_index=row_index,
                source_ref=dict(ref.get("source_ref") or {}),
            )
            return await self._dispatch_locked(slug, cmd)

    async def remove_reference(
        self,
        slug: str,
        reference_id: str,
    ) -> tuple[Workspace, DomainEvent]:
        """Remove a reference from the canvas bibliography.

        Emits a ``ReferenceRemoved`` domain event so SSE clients update.
        Raises ``CommandError`` for an unknown reference id. Same backend as
        the ``DELETE /references/{id}`` HTTP route, the ``canvas_remove_
        reference`` MCP tool, and ``anchor canvas reference remove`` CLI."""
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            refs = state.metadata.get("references")
            exists = isinstance(refs, list) and any(
                isinstance(r, dict) and r.get("id") == reference_id for r in refs
            )
            if not exists:
                raise CommandError(f"reference {reference_id!r} does not exist")
            return await self._dispatch_locked(
                slug, ReferenceRemoved(reference_id=reference_id),
            )

    async def update_reference(
        self,
        slug: str,
        reference_id: str,
        *,
        label: str | None = None,
    ) -> tuple[Workspace, DomainEvent]:
        """Edit a reference's human caption (``label``).

        Only ``label`` is mutable; the ``source_ref`` locator is immutable so
        the stored shape stays stable. ``label=None`` clears the caption.
        Emits a ``ReferenceUpdated`` domain event. Raises ``CommandError`` for
        an unknown reference id. Same backend as the ``PATCH /references/{id}``
        HTTP route, the ``canvas_update_reference`` MCP tool, and ``anchor
        canvas reference update`` CLI."""
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            refs = state.metadata.get("references")
            exists = isinstance(refs, list) and any(
                isinstance(r, dict) and r.get("id") == reference_id for r in refs
            )
            if not exists:
                raise CommandError(f"reference {reference_id!r} does not exist")
            return await self._dispatch_locked(
                slug, ReferenceUpdated(reference_id=reference_id, label=label),
            )

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

            node_likes = [
                NodeLike(id=n.id, x=n.x, y=n.y, width=n.width, height=n.height)
                for n in state.nodes.values()
            ]
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
            return await self._dispatch_locked(slug, cmd)

    async def _dispatch_locked(self, slug: str, cmd: BaseModel) -> tuple[Workspace, DomainEvent]:
        """Dispatch body assuming the caller already holds the workspace lock.

        Split out so ``add_node`` can read state (for auto-placement) and
        write the resulting command inside ONE lock acquisition — the
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
