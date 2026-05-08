"""SysmlService — orchestrates parser → mapper → workspace.

Pure orchestration over the ``SysmlParser`` / ``CanvasMapper`` ports and the
canvas-primitive ``WorkspaceService``. Three independent pipelines are
exposed:

  * ``render(text)`` — parse, map to canvas specs, dispatch as ``add_node`` /
    ``add_edge`` calls on the workspace.
  * ``export(slug)`` — Phase 1 stub: returns a header + TODO note. The
    extension point to fold in a real renderer later is the optional
    ``renderer`` argument on the constructor.

Every dispatch uses the existing ``WorkspaceService`` methods, so SysML nodes
are persisted, version-bumped, and broadcast on the SSE bus exactly like any
other canvas content.
"""
from __future__ import annotations

from typing import Any

from anchor.core.clock import Clock, SystemClock
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_sysml.core.events import (
    SysmlExported,
    SysmlRenderFailed,
    SysmlRendered,
)
from anchor.extensions.anchor_sysml.core.ports import (
    CanvasMapper,
    SysmlParser,
    SysmlRenderer,
)
from anchor.extensions.anchor_sysml.core.schemas import (
    CanvasBatch,
    Diagnostic,
    SysmlRenderResult,
)


class SysmlService:
    def __init__(
        self,
        *,
        workspace: WorkspaceService,
        bus: EventBus,
        parser: SysmlParser,
        mapper: CanvasMapper,
        renderer: SysmlRenderer | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.workspace = workspace
        self.bus = bus
        self.parser = parser
        self.mapper = mapper
        self.renderer = renderer
        self.clock: Clock = clock or SystemClock()

    async def render(
        self,
        *,
        workspace_slug: str,
        text: str,
        x_offset: float = 0,
        y_offset: float = 0,
        filename: str | None = None,
    ) -> SysmlRenderResult:
        try:
            ir = self.parser.parse(text, filename=filename)
            batch: CanvasBatch = self.mapper.map(ir, x_offset=x_offset, y_offset=y_offset)
            node_ids: list[str] = []
            edge_ids: list[str] = []
            diagnostics: list[Diagnostic] = list(batch.diagnostics)

            id_remap: dict[str, str] = {}  # mapper-supplied ids → real workspace ids
            for spec in batch.nodes:
                _, env = await self.workspace.add_node(
                    workspace_slug,
                    id=spec.id,
                    node_type=spec.node_type,
                    label=spec.label,
                    x=spec.x,
                    y=spec.y,
                    data=spec.data,
                )
                # ``add_node`` may have generated a fresh id if the supplied
                # one collides; record the actual id from the event payload.
                actual = env.payload.get("id", spec.id)
                id_remap[spec.id] = actual
                node_ids.append(actual)

            for spec in batch.edges:
                source = id_remap.get(spec.source, spec.source)
                target = id_remap.get(spec.target, spec.target)
                if source not in id_remap.values() or target not in id_remap.values():
                    diagnostics.append(
                        Diagnostic(
                            level="info",
                            message=(
                                f"edge skipped: unresolved endpoint "
                                f"{spec.source!r} → {spec.target!r}"
                            ),
                        )
                    )
                    continue
                _, env = await self.workspace.add_edge(
                    workspace_slug,
                    source=source,
                    target=target,
                    label=spec.label,
                    edge_type=spec.edge_type,
                    data=spec.data,
                )
                edge_ids.append(env.payload.get("id", ""))

            await self._publish(
                workspace_slug,
                SysmlRendered(
                    workspace_slug=workspace_slug,
                    node_count=len(node_ids),
                    edge_count=len(edge_ids),
                    diagnostic_count=len(diagnostics),
                    filename=filename,
                ),
            )
            return SysmlRenderResult(
                node_ids=node_ids,
                edge_ids=edge_ids,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            await self._publish(
                workspace_slug,
                SysmlRenderFailed(workspace_slug=workspace_slug, error=str(exc)),
            )
            raise

    async def export(self, *, workspace_slug: str) -> str:
        """Phase 1: return a stub. Real round-trip lands with the renderer
        port — see ``ports.SysmlRenderer``. The behaviour is documented in
        the extension README and the agent should not depend on a faithful
        export until Phase 2."""
        state = await self.workspace.get_state(workspace_slug)
        if self.renderer is not None:
            text = self.renderer.render(state)
        else:
            text = (
                "// Anchor SysML v2 export — Phase 1 stub.\n"
                "// TODO: implement faithful round-trip from canvas state to SysML v2 text.\n"
                f"// workspace: {workspace_slug}\n"
                f"// nodes: {len(state.get('nodes', []))}, edges: {len(state.get('edges', []))}\n"
            )
        await self._publish(
            workspace_slug,
            SysmlExported(workspace_slug=workspace_slug, char_count=len(text)),
        )
        return text

    async def _publish(self, workspace_slug: str, evt: Any) -> None:
        await self.bus.publish(
            DomainEvent(
                id=new_event_id(),
                ts=self.clock.now(),
                workspace_id=workspace_slug,
                type=evt.type,
                payload=evt.model_dump(),
            )
        )


__all__ = ["SysmlService"]
