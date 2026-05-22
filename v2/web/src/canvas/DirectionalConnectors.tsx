/**
 * DirectionalConnectors — Miro-style quick-connect overlay.
 *
 * Renders four small dots at the N/E/S/W midpoints of the currently
 * selected node and turns each one into a dual-purpose gesture:
 *
 *   - **Click** → create a peer of the same type, offset in that
 *     direction by `node_width + GAP_PX` (or `node_height + GAP_PX`),
 *     and wire a `floating` edge from the source to the new node. The
 *     new node is auto-selected so the user can type a label.
 *
 *   - **Drag**  → arrow preview tracks the pointer. On release:
 *       - over another node → just add the edge (same as a connect
 *         drag started from a Handle).
 *       - over empty pane   → open <QuickAddPopover> at the release
 *         point, with the source's type pre-highlighted. Picking a
 *         shape creates that node + edge in two API calls.
 *
 * Coordination notes:
 *
 *   - Selection state comes from ReactFlow's per-node `selected` flag
 *     via `useStore`, matching `NodeContextToolbar`. The connectors
 *     only render when **exactly one** node is selected — multi-select
 *     and zero-select hide them.
 *
 *   - Width/height are pulled from the canvas store's `data.width` /
 *     `data.height` (live-resize keeps these in sync). When unset, the
 *     fallback table below maps each shape's natural default.
 *
 *   - We mount this inside the ReactFlow provider (CanvasShell) so
 *     `useReactFlow().flowToScreenPosition` is available; all overlay
 *     elements use `position: fixed` so they sit above the React Flow
 *     viewport without needing to scale with the viewport transform.
 *
 *   - The shape primitives' `<Handle>` elements are untouched — this
 *     is a parallel overlay layer. The connector dots are not React
 *     Flow handles; they're plain DOM with their own pointer events,
 *     which is why dragging over another node is detected via
 *     `document.elementFromPoint` + closest `.react-flow__node`.
 *
 *   - ReactFlow drag (`onNodeDragStart` / `onNodeDragStop`) momentarily
 *     hides the dots so the two gestures don't fight. Wiring lives in
 *     `useUiStore.isDraggingNode`.
 */
import { useReactFlow, useStore } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { QuickAddPopover } from "./QuickAddPopover";

/** Pixel gap between the source node's edge and the new peer's edge. */
const PEER_GAP_PX = 80;

/** Natural default size when a node hasn't been resized yet. Mirrors the
 *  fallbacks in each shape primitive so the dots land on the visible edge. */
const DEFAULT_SIZE: Record<string, { width: number; height: number }> = {
  concept: { width: 160, height: 64 },
  entity: { width: 96, height: 96 },
  funnel: { width: 96, height: 96 },
  area: { width: 360, height: 220 },
  fact: { width: 220, height: 120 },
  note: { width: 220, height: 120 },
};

const FALLBACK_SIZE = { width: 160, height: 64 };

type Direction = "N" | "E" | "S" | "W";

type DragState = {
  direction: Direction;
  startScreen: { x: number; y: number };
  currentScreen: { x: number; y: number };
};

type PopoverState = {
  /** Screen-space anchor for the popover. */
  screen: { x: number; y: number };
  /** Flow-space drop target for the new node. */
  flow: { x: number; y: number };
  /** Source node id we'll wire an edge from. */
  sourceId: string;
  /** Source node type — pre-highlighted in the picker. */
  sourceType: string;
};

type Props = {
  workspaceSlug: string;
};

export function DirectionalConnectors({ workspaceSlug }: Props) {
  const rfNodes = useStore((s) => s.nodes);
  const transform = useStore((s) => s.transform);
  const { flowToScreenPosition, screenToFlowPosition } = useReactFlow();
  const nodes = useCanvasStore((s) => s.nodes);
  const isDraggingNode = useUiStore((s) => s.isDraggingNode);

  const selectedIds = useMemo(
    () => rfNodes.filter((n) => n.selected).map((n) => n.id),
    [rfNodes],
  );
  // Exactly-one-selected — multi-select hides the dots so we don't fight
  // the alignment / group-drag flow on NodeContextToolbar.
  const singleSelectedId = selectedIds.length === 1 ? selectedIds[0] : null;
  // Hover-mode: any hovered node also surfaces the dots (Miro-style). The
  // selection path takes priority — when one node is explicitly selected,
  // we anchor dots there even if the cursor wanders briefly. Otherwise we
  // follow the hover. Multi-select still suppresses the dots.
  const hoveredId = useUiStore((s) => s.hoveredNodeId);
  const effectiveId = singleSelectedId
    ?? (selectedIds.length === 0 && hoveredId ? hoveredId : null);
  const sourceNode = effectiveId ? nodes[effectiveId] : null;

  // Pointer-drag state lives in a ref so move handlers don't trigger
  // React re-renders on every pixel — only the arrow preview re-renders
  // through `setDragArrow`.
  const dragRef = useRef<DragState | null>(null);
  const [dragArrow, setDragArrow] = useState<DragState | null>(null);
  const [popover, setPopover] = useState<PopoverState | null>(null);

  // Recompute screen-space dot positions on selection / pan / zoom / resize.
  // Dots sit ~16 px (≈4 mm at 96 dpi) OUTSIDE the node's bounding rect on
  // each side so they don't visually fight with the NodeResizer corner/
  // edge handles that occupy the actual edge. The offset is in flow
  // coordinates and zooms naturally with the viewport.
  const dotPositions = useMemo(() => {
    if (!sourceNode) return null;
    const data = sourceNode.data as { width?: number; height?: number } | undefined;
    const defaultSize = DEFAULT_SIZE[sourceNode.node_type] ?? FALLBACK_SIZE;
    const w = data?.width ?? defaultSize.width;
    const h = data?.height ?? defaultSize.height;
    const { x, y } = sourceNode;
    // Flow-units offset away from the node edge. Picked so the dots sit
    // clear of NodeResizer's 10 px corner squares (±5 px around the edge)
    // and the floating mini-toolbar (lifted 40 px above the top edge).
    const OUTSET = 22;
    const n = flowToScreenPosition({ x: x + w / 2, y: y - OUTSET });
    const e = flowToScreenPosition({ x: x + w + OUTSET, y: y + h / 2 });
    const s = flowToScreenPosition({ x: x + w / 2, y: y + h + OUTSET });
    const wl = flowToScreenPosition({ x: x - OUTSET, y: y + h / 2 });
    return { N: n, E: e, S: s, W: wl, w, h };
    // `transform` is the trigger that re-runs this when ReactFlow pans/zooms.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceNode, transform]);

  /** Same-type peer creation. The new node gets focused for inline rename. */
  const createPeer = useCallback(
    async (direction: Direction, sourceType: string, srcId: string, srcW: number, srcH: number, sx: number, sy: number) => {
      const offset = {
        N: { dx: 0, dy: -(srcH + PEER_GAP_PX) },
        E: { dx: srcW + PEER_GAP_PX, dy: 0 },
        S: { dx: 0, dy: srcH + PEER_GAP_PX },
        W: { dx: -(srcW + PEER_GAP_PX), dy: 0 },
      }[direction];
      const newPos = { x: sx + offset.dx, y: sy + offset.dy };
      try {
        const res = (await canvases.addNode(workspaceSlug, {
          node_type: sourceType,
          label: "",
          x: newPos.x,
          y: newPos.y,
          data: {},
        })) as { event?: { payload?: { id?: string } } } | null;
        const newId = res?.event?.payload?.id;
        if (!newId) return;
        await canvases.addEdge(workspaceSlug, {
          source: srcId,
          target: newId,
          edge_type: "floating",
          data: {},
        });
        // Promote the new node into the single selection so its inline
        // label input gets focused (shape primitives gate editing on
        // `selected`; the rfNodes effect rebuilds selection from the
        // store/rfNodes on every SSE patch, so we stamp the UI store
        // id too — NodeContextToolbar uses that for single-node ops).
        useUiStore.getState().setSelectedNodeId(newId);
        // Defer until the SSE-driven render lands the new rfNode, then
        // flip its `selected` flag and trigger inline rename via the
        // `pendingInlineRenameNodeId` channel below.
        useUiStore.getState().requestInlineRename(newId);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("directional peer creation failed", err);
      }
    },
    [workspaceSlug],
  );

  /** Click handler for a dot — creates the peer immediately. */
  const onDotClick = useCallback(
    (direction: Direction) => {
      if (!sourceNode || !dotPositions) return;
      void createPeer(
        direction,
        sourceNode.node_type,
        sourceNode.id,
        dotPositions.w,
        dotPositions.h,
        sourceNode.x,
        sourceNode.y,
      );
    },
    [sourceNode, dotPositions, createPeer],
  );

  // Window-level pointer move / up so the user can drag well past the
  // dot's 20×20 hit area. Bound once per active drag.
  useEffect(() => {
    if (!dragArrow) return;
    const handleMove = (event: PointerEvent) => {
      const next: DragState = {
        ...dragRef.current!,
        currentScreen: { x: event.clientX, y: event.clientY },
      };
      dragRef.current = next;
      setDragArrow(next);
    };
    const handleUp = (event: PointerEvent) => {
      const drag = dragRef.current;
      dragRef.current = null;
      setDragArrow(null);
      if (!drag || !sourceNode) return;
      // Test what's under the release point. ReactFlow tags every node
      // wrapper with `.react-flow__node` and `data-id` — we filter on the
      // class to avoid matching edges (`.react-flow__edge`) which also
      // carry `data-id`. `closest()` walks up the DOM so children
      // (Handles, labels, …) all resolve to the same wrapper.
      const releaseTarget = document.elementFromPoint(event.clientX, event.clientY);
      const nodeEl = releaseTarget?.closest(".react-flow__node") as HTMLElement | null;
      const targetId = nodeEl?.dataset?.id;
      if (targetId && targetId !== sourceNode.id) {
        // Drop on existing node → just create the edge.
        void canvases
          .addEdge(workspaceSlug, {
            source: sourceNode.id,
            target: targetId,
            edge_type: "floating",
            data: {},
          })
          .catch((err) => {
            // eslint-disable-next-line no-console
            console.error("directional edge-to-node failed", err);
          });
        return;
      }
      // Empty pane → open the popover. Convert the release point to flow
      // coords so the eventual node lands exactly under the cursor.
      const flow = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      setPopover({
        screen: { x: event.clientX, y: event.clientY },
        flow,
        sourceId: sourceNode.id,
        sourceType: sourceNode.node_type,
      });
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [dragArrow, sourceNode, workspaceSlug, screenToFlowPosition]);

  const onDotPointerDown = useCallback(
    (event: React.PointerEvent, direction: Direction) => {
      if (!dotPositions) return;
      // Suppress the canvas's own armed-tool / pane handlers; this gesture
      // belongs to the connector layer.
      event.stopPropagation();
      // Only handle left-button for connect drag — right click should go
      // to the context menu, middle click to viewport pan.
      if (event.button !== 0) return;
      const origin = dotPositions[direction];
      const drag: DragState = {
        direction,
        startScreen: { x: origin.x, y: origin.y },
        currentScreen: { x: event.clientX, y: event.clientY },
      };
      dragRef.current = drag;
      setDragArrow(drag);
    },
    [dotPositions],
  );

  // Clicks land via `onClick` only when no drag started (or pointer-up
  // happened in-place). React doesn't distinguish, so we check the drag
  // distance: < 4 px between down and up means the user clicked. Without
  // this check, every click would briefly arm a drag and then create a
  // popover on release.
  const onDotClickEvent = useCallback(
    (event: React.MouseEvent, direction: Direction) => {
      event.stopPropagation();
      const drag = dragRef.current;
      if (drag) {
        const dx = drag.currentScreen.x - drag.startScreen.x;
        const dy = drag.currentScreen.y - drag.startScreen.y;
        if (Math.hypot(dx, dy) >= 4) return;
      }
      onDotClick(direction);
    },
    [onDotClick],
  );

  if (!sourceNode || !dotPositions || isDraggingNode) {
    // Even with no dots, the popover may still be open mid-creation —
    // render it independently so it survives the next state update.
    return popover ? (
      <QuickAddPopover
        workspaceSlug={workspaceSlug}
        screenAnchor={popover.screen}
        flowDrop={popover.flow}
        sourceId={popover.sourceId}
        sourceType={popover.sourceType}
        onClose={() => setPopover(null)}
      />
    ) : null;
  }

  const dragging = dragArrow !== null;

  return (
    <>
      {/* Dots — hidden during an in-flight drag so the user sees only
          the arrow preview. `pointer-events-auto` overrides the canvas
          wrapper if any ancestor turned it off. */}
      {(["N", "E", "S", "W"] as const).map((dir) => {
        const pos = dotPositions[dir];
        return (
          <button
            key={dir}
            type="button"
            aria-label={`Add ${dir} peer`}
            data-testid={`connector-dot-${dir}`}
            onPointerDown={(e) => onDotPointerDown(e, dir)}
            onClick={(e) => onDotClickEvent(e, dir)}
            style={{
              position: "fixed",
              left: pos.x - 10,
              top: pos.y - 10,
              width: 20,
              height: 20,
              padding: 0,
              border: "none",
              background: "transparent",
              cursor: "crosshair",
              pointerEvents: dragging ? "none" : "auto",
              opacity: dragging ? 0 : 1,
              zIndex: 28,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            // Wrap a 12×12 inner pill so the visible dot is centred in a
            // 20×20 hit area (Miro-style: generous click target around a
            // small affordance).
          >
            <span
              aria-hidden
              className="block h-3 w-3 rounded-full border border-white/70 bg-neutral-400 transition hover:scale-125 hover:border-sky-500 hover:bg-sky-500"
              style={{ boxShadow: "0 1px 2px rgba(0,0,0,0.15)" }}
            />
          </button>
        );
      })}

      {/* Drag arrow preview. SVG canvas covers the viewport so we don't
          have to worry about clipping. `pointer-events-none` so the move
          handlers on `window` still get every pointermove (without this,
          the SVG would absorb the pointer mid-drag). */}
      {dragArrow ? (
        <svg
          style={{
            position: "fixed",
            inset: 0,
            width: "100vw",
            height: "100vh",
            pointerEvents: "none",
            zIndex: 27,
          }}
          aria-hidden
          data-testid="directional-drag-arrow"
        >
          <defs>
            <marker
              id="directional-arrowhead"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path d="M0,0 L10,5 L0,10 z" fill="#0ea5e9" />
            </marker>
          </defs>
          {(() => {
            const a = dragArrow.startScreen;
            const b = dragArrow.currentScreen;
            // Bezier control points pulled along the drag axis — gives a
            // soft S-curve that doesn't fight short drags. Same maths
            // the FloatingEdge bezier uses.
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const pull = Math.min(120, Math.hypot(dx, dy) * 0.4);
            const c1 = { x: a.x + Math.sign(dx) * pull, y: a.y };
            const c2 = { x: b.x - Math.sign(dx) * pull, y: b.y };
            return (
              <path
                d={`M ${a.x} ${a.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${b.x} ${b.y}`}
                stroke="#0ea5e9"
                strokeWidth={1.5}
                fill="none"
                markerEnd="url(#directional-arrowhead)"
                opacity={0.85}
              />
            );
          })()}
        </svg>
      ) : null}

      {popover ? (
        <QuickAddPopover
          workspaceSlug={workspaceSlug}
          screenAnchor={popover.screen}
          flowDrop={popover.flow}
          sourceId={popover.sourceId}
          sourceType={popover.sourceType}
          onClose={() => setPopover(null)}
        />
      ) : null}
    </>
  );
}
