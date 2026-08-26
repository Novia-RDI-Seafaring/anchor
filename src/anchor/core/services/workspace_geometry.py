"""Server-authoritative multi-node geometry operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from anchor.core.clock import Clock
from anchor.core.events.canvas import NodeMoved
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id
from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.workspace_locks import WorkspaceLocks
from anchor.core.ports.workspace_store import WorkspaceStore
from anchor.core.workspace.align import Anchor, Axis, SelectedNode
from anchor.core.workspace.align import align_nodes as align_nodes_pure
from anchor.core.workspace.align import distribute_nodes as distribute_nodes_pure
from anchor.core.workspace.layout import EdgeLike, NodeLike
from anchor.core.workspace.layout import organize_subtree as organize_subtree_pure
from anchor.core.workspace.reducer import apply
from anchor.core.workspace.workspace import CommandError, Workspace


class WorkspaceGeometryOperations:
    """Compute and atomically persist workspace layout changes."""

    def __init__(
        self,
        store: WorkspaceStore,
        bus: EventBus,
        locks: WorkspaceLocks,
        clock: Clock,
    ) -> None:
        self.store = store
        self.bus = bus
        self.locks = locks
        self.clock = clock

    async def organize_subtree(
        self,
        slug: str,
        root_id: str,
        *,
        orientation: Literal["vertical", "horizontal"] = "vertical",
        algo: Literal["dagre"] = "dagre",
        direction: Literal["outgoing", "incoming", "any"] = "any",
    ) -> tuple[Workspace, list[DomainEvent]]:
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

            nodes = [
                NodeLike(id=node.id, x=node.x, y=node.y, width=node.width, height=node.height)
                for node in state.nodes.values()
            ]
            edges = [
                EdgeLike(source=edge.source, target=edge.target)
                for edge in state.edges.values()
            ]
            placements = organize_subtree_pure(
                nodes,
                edges,
                root_id,
                orientation=orientation,
                direction=direction,
            )
            return await self._persist_moves(slug, state, placements)

    async def align_nodes(
        self,
        slug: str,
        ids: list[str],
        anchor: Anchor,
    ) -> tuple[Workspace, list[DomainEvent]]:
        return await self._geometry_operation(
            slug,
            ids,
            lambda items: align_nodes_pure(items, anchor),
            label=f"align {anchor!r}",
            minimum=2,
        )

    async def distribute_nodes(
        self,
        slug: str,
        ids: list[str],
        axis: Axis,
    ) -> tuple[Workspace, list[DomainEvent]]:
        return await self._geometry_operation(
            slug,
            ids,
            lambda items: distribute_nodes_pure(items, axis),
            label=f"distribute {axis!r}",
            minimum=3,
        )

    async def _geometry_operation(
        self,
        slug: str,
        ids: list[str],
        compute: Callable[[list[SelectedNode]], dict[str, tuple[float, float]]],
        *,
        label: str,
        minimum: int,
    ) -> tuple[Workspace, list[DomainEvent]]:
        if len(ids) < minimum:
            raise CommandError(f"{label} needs at least {minimum} nodes; got {len(ids)}")
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            missing = [node_id for node_id in ids if node_id not in state.nodes]
            if missing:
                raise CommandError(
                    f"{label}: nodes do not exist: {sorted(missing)!r}",
                )
            selected = [
                SelectedNode(
                    id=node_id,
                    x=state.nodes[node_id].x,
                    y=state.nodes[node_id].y,
                    width=state.nodes[node_id].width,
                    height=state.nodes[node_id].height,
                )
                for node_id in ids
            ]
            return await self._persist_moves(slug, state, compute(selected))

    async def _persist_moves(
        self,
        slug: str,
        state: Workspace,
        placements: dict[str, tuple[float, float]],
    ) -> tuple[Workspace, list[DomainEvent]]:
        moves = [
            (node_id, x, y)
            for node_id, (x, y) in placements.items()
            if (node := state.nodes.get(node_id)) is not None
            and (node.x != x or node.y != y)
        ]
        if not moves:
            return state, []

        envelopes: list[DomainEvent] = []
        new_state = state
        cause = new_event_id()
        for node_id, x, y in moves:
            event = NodeMoved(id=node_id, x=x, y=y)
            envelope = DomainEvent(
                id=new_event_id(),
                ts=self.clock.now(),
                workspace_id=slug,
                type=event.type,
                payload=event.model_dump(),
                causation_id=cause,
            )
            version = await self.store.append_event(slug, envelope)
            envelope.version = version
            new_state = apply(new_state, event)
            new_state.version = version
            new_state.last_event_id = envelope.id
            envelopes.append(envelope)

        await self.store.snapshot(slug, new_state)
        for envelope in envelopes:
            await self.bus.publish(envelope)
        return new_state, envelopes
