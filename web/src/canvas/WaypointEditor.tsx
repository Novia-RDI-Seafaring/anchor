/**
 * WaypointEditor — overlay that renders draggable waypoint handles for
 * the currently-selected edge when it's routed via `smooth` / `step` /
 * `straight`. For `floating` / `anchored` edges the overlay is silent —
 * those routers auto-route and ignore waypoints.
 *
 * Two kinds of handle:
 *   - REAL waypoint (filled blue dot, hollow centre) — already persisted
 *     in `edge.data.waypoints`. Drag to reposition; persisted on drop.
 *   - GHOST midpoint (small filled blue dot) — one per segment of the
 *     current polyline (source → wp1 → wp2 → … → target). Drag a ghost
 *     to materialise a new waypoint at that segment's mid-drag position;
 *     the ghost upgrades to a real waypoint on release.
 *
 * The DOM layer sits on top of ReactFlow's viewport so we convert flow
 * coordinates → screen coordinates each render. Subscribing to
 * `useStore((s) => s.transform)` re-renders on pan/zoom.
 *
 * Coordinates stored on the edge are FLOW-space. Drag math converts
 * back through `screenToFlowPosition`.
 */
import { useReactFlow, useStore } from "@xyflow/react";
import { useCallback, useMemo, useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { resolveEdgeUserStyle } from "./edges/edge-style";

type Props = {
  workspaceSlug: string;
};

const ROUTED_TYPES = new Set(["smooth", "step", "straight"]);

function nodeCentre(n: {
  x: number;
  y: number;
  data?: Record<string, unknown>;
} | undefined): { x: number; y: number } | null {
  if (!n) return null;
  const w = (n.data?.width as number | undefined) ?? 100;
  const h = (n.data?.height as number | undefined) ?? 100;
  return { x: n.x + w / 2, y: n.y + h / 2 };
}

export function WaypointEditor({ workspaceSlug }: Props) {
  const transform = useStore((s) => s.transform);
  const { flowToScreenPosition, screenToFlowPosition } = useReactFlow();
  const selectedEdgeId = useUiStore((s) => s.selectedEdgeId);
  const edges = useCanvasStore((s) => s.edges);
  const nodes = useCanvasStore((s) => s.nodes);

  const edge = selectedEdgeId ? edges[selectedEdgeId] ?? null : null;

  // Local drag state — index of the waypoint being dragged (or "ghost-{i}"
  // for the in-flight materialisation of a new waypoint from a segment
  // midpoint), plus the live flow-space position.
  const [drag, setDrag] = useState<{ kind: "real" | "ghost"; index: number; x: number; y: number } | null>(null);
  const dragRef = useRef<typeof drag>(null);
  dragRef.current = drag;

  const persistWaypoints = useCallback(async (waypoints: Array<{ x: number; y: number }>) => {
    if (!edge) return;
    const data = { ...(edge.data ?? {}), waypoints };
    try { await canvases.patchEdge(workspaceSlug, edge.id, { data }); }
    catch (err) {
      // eslint-disable-next-line no-console
      console.error("waypoint persist failed", err);
    }
  }, [edge, workspaceSlug]);

  const screenPoints = useMemo(() => {
    if (!edge) return null;
    if (!ROUTED_TYPES.has(edge.edge_type)) return null;
    const src = nodeCentre(nodes[edge.source]);
    const tgt = nodeCentre(nodes[edge.target]);
    if (!src || !tgt) return null;
    const user = resolveEdgeUserStyle(edge.data);
    if (user.locked) return null;
    const realFlow = user.waypoints;
    // Build the polyline in flow space + ghost positions (segment midpoints).
    const polyFlow = [src, ...realFlow, tgt];
    const ghostsFlow: Array<{ x: number; y: number }> = [];
    for (let i = 0; i < polyFlow.length - 1; i++) {
      const a = polyFlow[i]!;
      const b = polyFlow[i + 1]!;
      ghostsFlow.push({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    }
    return {
      real: realFlow.map((p) => ({ ...p, screen: flowToScreenPosition(p) })),
      ghosts: ghostsFlow.map((p, i) => ({ index: i, screen: flowToScreenPosition(p) })),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edge, nodes, transform]);

  if (!edge || !screenPoints) return null;

  const user = resolveEdgeUserStyle(edge.data);
  const realWaypoints = user.waypoints;

  const startDragReal = (index: number) => (ev: React.PointerEvent) => {
    ev.stopPropagation();
    ev.preventDefault();
    (ev.target as HTMLElement).setPointerCapture(ev.pointerId);
    const flow = screenToFlowPosition({ x: ev.clientX, y: ev.clientY });
    setDrag({ kind: "real", index, x: flow.x, y: flow.y });
  };

  const startDragGhost = (index: number) => (ev: React.PointerEvent) => {
    ev.stopPropagation();
    ev.preventDefault();
    (ev.target as HTMLElement).setPointerCapture(ev.pointerId);
    const flow = screenToFlowPosition({ x: ev.clientX, y: ev.clientY });
    setDrag({ kind: "ghost", index, x: flow.x, y: flow.y });
  };

  const onMove = (ev: React.PointerEvent) => {
    if (!dragRef.current) return;
    const flow = screenToFlowPosition({ x: ev.clientX, y: ev.clientY });
    setDrag({ ...dragRef.current, x: flow.x, y: flow.y });
  };

  const onUp = () => {
    const d = dragRef.current;
    if (!d) return;
    const next = realWaypoints.slice();
    if (d.kind === "real") {
      next[d.index] = { x: d.x, y: d.y };
    } else {
      // Insert at ghost.index, which sits between segment `index - 1` and
      // `index` in the existing waypoint list. ghost 0 → before wp 0, etc.
      next.splice(d.index, 0, { x: d.x, y: d.y });
    }
    setDrag(null);
    void persistWaypoints(next);
  };

  // Optimistic during drag: re-derive the displayed polyline if needed.
  const dragOverlayPos = drag ? flowToScreenPosition({ x: drag.x, y: drag.y }) : null;

  return (
    <svg
      data-testid="waypoint-editor"
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 25,
      }}
      aria-hidden
    >
      {/* Ghost midpoints (small filled dots). */}
      {screenPoints.ghosts.map((g) => (
        <circle
          key={`gh-${g.index}`}
          cx={g.screen.x}
          cy={g.screen.y}
          r={4}
          fill="#0ea5e9"
          fillOpacity={0.6}
          stroke="#ffffff"
          strokeWidth={1}
          style={{ pointerEvents: "auto", cursor: "grab" }}
          onPointerDown={startDragGhost(g.index)}
          onPointerMove={onMove}
          onPointerUp={onUp}
          data-testid={`waypoint-ghost-${g.index}`}
        />
      ))}
      {/* Real waypoints (hollow circles). */}
      {screenPoints.real.map((p, i) => (
        <circle
          key={`wp-${i}`}
          cx={p.screen.x}
          cy={p.screen.y}
          r={6}
          fill="#ffffff"
          stroke="#0ea5e9"
          strokeWidth={2}
          style={{ pointerEvents: "auto", cursor: "grab" }}
          onPointerDown={startDragReal(i)}
          onPointerMove={onMove}
          onPointerUp={onUp}
          data-testid={`waypoint-real-${i}`}
        />
      ))}
      {/* Live drag indicator. */}
      {dragOverlayPos ? (
        <circle
          cx={dragOverlayPos.x}
          cy={dragOverlayPos.y}
          r={7}
          fill="#0ea5e9"
          fillOpacity={0.3}
          stroke="#0ea5e9"
          strokeWidth={1.5}
        />
      ) : null}
    </svg>
  );
}
