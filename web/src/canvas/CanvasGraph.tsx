import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Node as RfNode,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { breadcrumb } from "@/canvas/breadcrumb";
import { AnchoredEdge } from "@/canvas/edges/AnchoredEdge";
import { EdgeMarkerDefs } from "@/canvas/edges/EdgeMarkerDefs";
import { FloatingEdge } from "@/canvas/edges/FloatingEdge";
import { SmoothEdge, StepEdge, StraightEdge } from "@/canvas/edges/RoutedEdge";
import { EdgeContextMenu, type EdgeContextMenuTarget } from "@/canvas/EdgeContextMenu";
import { EdgeContextToolbar } from "@/canvas/EdgeContextToolbar";
import { NodeContextMenu, type ContextMenuTarget } from "@/canvas/NodeContextMenu";
import { NodeContextToolbar } from "@/canvas/NodeContextToolbar";
import { WaypointEditor } from "@/canvas/WaypointEditor";
import {
  ancestorOffset,
  canvasNodeSize,
} from "@/canvas/canvasProjection";
import {
  PaintGhost,
} from "@/canvas/PaintGhost";
import { nodeTypes } from "@/canvas/registry";
import { UploadJobsOverlay } from "@/canvas/UploadJobsOverlay";
import { useArmedToolPlacement } from "@/canvas/useArmedToolPlacement";
import { useCanvasDrop } from "@/canvas/useCanvasDrop";
import { useCanvasFlowState } from "@/canvas/useCanvasFlowState";
import { refreshWorkspaces } from "@/canvas/useWorkspacesList";
import { CanvasSse, type CanvasEvent } from "@/realtime/sseClient";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

// Custom edge renderers keyed by the `edge_type` string the backend emits.
// `floating` = loose graph edge. `anchored` = handle-keyed (port → port,
// evidence row → bbox). `smooth` / `step` / `straight` are the Miro-style
// user-pickable routing modes; the user picks them from EdgeContextToolbar
// and we serialise via `update_edge` → `edge_type=<mode>`.
//
// The dispatcher inside each component switches on the user-pickable cap /
// stroke / colour fields (see `canvas/edges/edge-style.ts`), with the
// legacy SysML `data.marker` system layered underneath for backwards
// compatibility.
const edgeTypes = {
  floating: FloatingEdge,
  anchored: AnchoredEdge,
  smooth: SmoothEdge,
  step: StepEdge,
  straight: StraightEdge,
};

type Props = {
  slug: string;
  /**
   * When true, the canvas becomes a pure projection of state — no drag,
   * no drop, no dblclick handlers. Subscribes to SSE and renders. Used by
   * the standalone monitor window at `/m/:id` and by any future read-only
   * rendering target (XR overlays, headless screenshot service, ...).
   *
   * When false (default), the canvas accepts interactions: nodes are
   * draggable, files dropped on the canvas trigger ingest, double-click
   * opens the PDF viewer, and shell-driven payloads (Palette/Library
   * drops) instantiate nodes via the HTTP API.
   */
  readOnly?: boolean;
};

function workspaceListMayChange(evt: CanvasEvent): boolean {
  switch (evt.type) {
    case "NodeAdded":
    case "NodeRemoved":
    case "NodeUpdated":
    case "EdgeAdded":
    case "EdgeRemoved":
    case "CanvasCleared":
      return true;
    default:
      return false;
  }
}

export function CanvasGraph({ slug, readOnly = false }: Props) {
  // ReactFlowProvider is mounted by CanvasShell when present. For bare uses
  // (e.g. the monitor route at /m/:id), wrap in a provider here.
  if (readOnly) {
    return (
      <ReactFlowProvider>
        <CanvasGraphInner slug={slug} readOnly />
      </ReactFlowProvider>
    );
  }
  return <CanvasGraphInner slug={slug} readOnly={false} />;
}

function CanvasGraphInner({ slug, readOnly = false }: Props) {
  const setSnapshot = useCanvasStore((s) => s.setSnapshot);
  const applyEvent = useCanvasStore((s) => s.applyEvent);
  const reset = useCanvasStore((s) => s.reset);
  const { screenToFlowPosition } = useReactFlow();
  const openPdf = useUiStore((s) => s.openPdf);
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
  // Drives the floating↔anchored swap on evidence edges. When something
  // broadcasts a hovered source_ref (spec-row hover, region hover, an edge
  // hover that reflects back) the matching evidence edge flips from
  // node-to-node float to row-handle→region-handle anchored.
  // Drives the hover-thicken provenance path (#183). When the pointer is
  // over a node, we light up the evidence edge(s) tracing that node back to
  // its source document and quiet the rest of the bundle. This composes with
  // the row-level `hoveredSourceRef` swap above — both feed the same per-edge
  // active/dimmed flags the evidence renderers already understand.
  const setSelectedNodeId = useUiStore((s) => s.setSelectedNodeId);
  const setSelectedEdgeId = useUiStore((s) => s.setSelectedEdgeId);
  const setPropertiesOpen = useUiStore((s) => s.setPropertiesOpen);
  const navigate = useNavigate();
  const { armedTool, paintRect, pointerHandlers } = useArmedToolPlacement(
    slug,
    screenToFlowPosition,
  );
  const { rootRef, onDragOver, onDrop, uploadJobs } = useCanvasDrop(
    slug,
    screenToFlowPosition,
  );

  // ReactFlow needs to own the per-frame drag position. We seed its internal
  // node list from the Zustand store and re-seed whenever the store changes
  // (snapshot, SSE patch, etc.). `onNodesChange` lets ReactFlow update its
  // own state during drag/select/etc.
  const { rfNodes, rfEdges, onNodesChange, onEdgesChange, onConnect } = useCanvasFlowState(
    slug,
    readOnly,
  );
  // Right-click menu target. Null when no context menu is open. Set by
  // `onNodeContextMenu` and cleared by selection / outside-click / Esc.
  const [contextMenuTarget, setContextMenuTarget] = useState<ContextMenuTarget | null>(null);
  // Edge right-click menu target. Set by `onEdgeContextMenu`. Same
  // dismissal contract as the node menu (Esc / outside / item-pick).
  const [edgeContextTarget, setEdgeContextTarget] = useState<EdgeContextMenuTarget | null>(null);

  useEffect(() => {
    let cancelled = false;
    reset();
    canvases.state(slug).then((snap) => {
      if (!cancelled) setSnapshot(snap);
    }).catch(() => {});
    const sse = new CanvasSse(slug, {
      onSnapshot: (snap) => {
        if (cancelled) return;
        setSnapshot(snap as Parameters<typeof setSnapshot>[0]);
      },
      onPatch: (evt) => {
        applyEvent(evt);
        if (workspaceListMayChange(evt)) {
          refreshWorkspaces().catch(() => {});
        }
      },
    });
    sse.connect();
    return () => {
      cancelled = true;
      sse.disconnect();
    };
  }, [slug, applyEvent, reset, setSnapshot]);

  /**
   * Find the topmost Area whose body contains the given canvas point.
   *
   * Used by `onNodeDrag` to telegraph "drop here to nest" via the Area's
   * highlight state and by `onNodeDragStop` to commit the reparent.
   *
   * Reads rect from `useCanvasStore` (x, y, width, height) rather than the
   * live ReactFlow rfNode positions — Areas don't move during a child's
   * drag, so the store position is authoritative. Skips the dragged node
   * itself (a node can't be its own ancestor) and any descendants of the
   * dragged node (would create a cycle).
   *
   * When the cursor sits inside multiple nested Areas, returns the
   * innermost one (smallest area), giving the natural drop semantics.
   */
  const findAreaAtPoint = useCallback(
    (point: { x: number; y: number }, draggedId: string): string | null => {
      const storeState = useCanvasStore.getState();
      // Build the set of descendants of the dragged node so we never
      // suggest reparenting onto one of our own children.
      const descendants = new Set<string>();
      const stack = [draggedId];
      while (stack.length) {
        const cur = stack.pop()!;
        for (const n of Object.values(storeState.nodes)) {
          if (n.parent === cur && !descendants.has(n.id)) {
            descendants.add(n.id);
            stack.push(n.id);
          }
        }
      }
      let best: { id: string; area: number } | null = null;
      for (const n of Object.values(storeState.nodes)) {
        if (n.node_type !== "area") continue;
        if (n.id === draggedId) continue;
        if (descendants.has(n.id)) continue;
        const size = canvasNodeSize(n);
        const w = size.width ?? 320;
        const h = size.height ?? 200;
        // Area position in flow coords is its own (x, y) when it has no
        // parent; when nested, ReactFlow stores parent-relative — but the
        // canvas store mirrors the wire `x`, `y` which the backend keeps
        // in flow coords too. The acme-org canvas (the verification case)
        // uses top-level Areas; nested-Area drop targeting is a known
        // follow-up.
        if (
          point.x >= n.x
          && point.x <= n.x + w
          && point.y >= n.y
          && point.y <= n.y + h
        ) {
          const a = w * h;
          if (!best || a < best.area) best = { id: n.id, area: a };
        }
      }
      return best?.id ?? null;
    },
    [],
  );

  /**
   * onNodeDrag — fires continuously while the user drags ANY node.
   *
   * We compute the dragged node's centre in flow coordinates, find the
   * (innermost) Area whose body contains that point, and stash the id on
   * uiStore. The Area's renderer subscribes to that id and renders the
   * "drop here" highlight while it matches.
   *
   * Areas themselves don't trigger highlights when dragged — we don't
   * want a moved Area to highlight the Area it happens to pass over.
   */
  const onNodeDrag = useCallback(
    (_event: React.MouseEvent, draggedNode: RfNode) => {
      if (readOnly) return;
      if (draggedNode.type === "area") return;
      // Use the node's own bounding box centre. ReactFlow gives us
      // `position` (top-left in flow coords) and the measured `width` /
      // `height` once the node has been rendered.
      const w = draggedNode.width ?? 0;
      const h = draggedNode.height ?? 0;
      const centre = {
        x: draggedNode.position.x + w / 2,
        y: draggedNode.position.y + h / 2,
      };
      const target = findAreaAtPoint(centre, draggedNode.id);
      const current = useUiStore.getState().dropTargetAreaId;
      if (current !== target) useUiStore.getState().setDropTargetAreaId(target);
    },
    [readOnly, findAreaAtPoint],
  );

  // In readOnly mode the canvas becomes a pure projection: no drags, no
  // drops, no dblclick → viewer. It still subscribes to SSE so any state
  // change emitted by the rest of the system shows up live.
  return (
    <div
      ref={rootRef}
      className={`relative h-full w-full ${armedTool ? "cursor-crosshair" : ""}`}
      {...(readOnly
        ? {}
        : {
            onDragOver,
            onDrop,
            ...pointerHandlers,
          })}
    >
      {/* Mount custom <marker> defs once per canvas. Edge components
          reference them by URL fragment (`url(#anchor-mk-...)`); SVG
          marker IDs resolve document-wide so a sibling defs SVG works. */}
      <EdgeMarkerDefs />
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
        zoomOnScroll
        // When a paint tool is armed, disable pan-on-drag so the user's
        // drag draws the shape instead of moving the viewport. We still
        // permit middle-click pan (`[1]`) and right-click pan (`[2]`) so
        // the user can reposition the canvas without disarming the tool.
        panOnDrag={armedTool ? [1, 2] : true}
        // Shift+click adds to selection. Shift+drag still does rubber-band
        // selection — ReactFlow distinguishes the two gestures even when
        // they share a modifier.
        multiSelectionKeyCode="Shift"
        selectionKeyCode="Shift"
        deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
        // Edge hover broadcasts the edge's source_ref so the corresponding
        // document node can highlight the region. Used by evidence edges
        // (spec node → document node).
        onEdgeMouseEnter={(_event, edge) => {
          const data = edge.data as
            | { source_ref?: { kind?: string; page?: number; bbox?: number[] } }
            | undefined;
          const ref = data?.source_ref;
          if (!ref?.page) return;
          // Resolve the target node to learn the document slug.
          const tgt = useCanvasStore.getState().nodes[edge.target];
          const tgtData = tgt?.data as { slug?: string } | undefined;
          if (tgtData?.slug) {
            setHoveredSourceRef({
              slug: tgtData.slug,
              page: ref.page,
              bbox: ref.bbox,
            });
          }
        }}
        onEdgeMouseLeave={() => clearHoveredSourceRef()}
        {...(readOnly
          ? {}
          : {
              // Selection no longer auto-opens the right Properties Panel
              // (Miro-style mini-toolbar is the default affordance; the
              // panel is reachable via the toolbar's ⋮ More or the
              // context menu's "Edit properties…").
              onNodeClick: (_event, node) => { setSelectedNodeId(node.id); },
              // Hover state is no longer consumed by DirectionalConnectors
              // (the dots are selection-only now), but other UI may still
              // want to know which node the cursor is over. Plain
              // immediate set/clear, no deferred-clear gymnastics.
              onNodeMouseEnter: (_event, node) => {
                useUiStore.getState().setHoveredNodeId(node.id);
              },
              onNodeMouseLeave: () => {
                useUiStore.getState().setHoveredNodeId(null);
              },
              onEdgeClick: (_event, edge) => { setSelectedEdgeId(edge.id); },
              onEdgeContextMenu: (event, edge) => {
                event.preventDefault();
                setSelectedEdgeId(edge.id);
                setEdgeContextTarget({ x: event.clientX, y: event.clientY, edgeId: edge.id });
              },
              onPaneClick: () => {
                setSelectedNodeId(null);
                setSelectedEdgeId(null);
                setPropertiesOpen(false);
                setContextMenuTarget(null);
                setEdgeContextTarget(null);
              },
              onNodeContextMenu: (event, node) => {
                event.preventDefault();
                // ReactFlow promotes the right-clicked node into the
                // selection if it wasn't already there. Read the current
                // rfNodes state to capture the full multi-select.
                const selectedIds = rfNodes.filter((n) => n.selected).map((n) => n.id);
                if (!selectedIds.includes(node.id)) selectedIds.push(node.id);
                const hasEdges = Object.values(useCanvasStore.getState().edges).some(
                  (e) => e.source === node.id || e.target === node.id,
                );
                setContextMenuTarget({
                  x: event.clientX,
                  y: event.clientY,
                  nodeId: node.id,
                  selectedIds,
                  hasEdges,
                });
                // Stamp the most-recently-clicked id so "Edit properties…"
                // from the menu scopes the panel correctly.
                setSelectedNodeId(node.id);
              },
              onNodeDoubleClick: (_event, node) => {
                if (node.type === "document") {
                  const data = node.data as { slug?: string; status?: string } | undefined;
                  const status = data?.status ?? "ready";
                  if (data?.slug && (status === "ready" || status === "found")) {
                    openPdf(data.slug, {
                      workspaceSlug: slug,
                      documentNodeId: node.id,
                    });
                  }
                  return;
                }
                // Sub-canvas drill-down. The breadcrumb chain is updated by
                // CanvasPage on mount of the destination route; we just
                // navigate. Cycle prevention: if the target slug is already
                // in the chain, refuse to drill — the SubCanvasPrimitive
                // shows an "↩ already visiting" badge for visual feedback.
                if (node.type === "canvas") {
                  const data = node.data as { canvas_slug?: string } | undefined;
                  const target = data?.canvas_slug;
                  if (!target) return;
                  if (breadcrumb.includes(target)) return;
                  breadcrumb.enter(target);
                  navigate(`/c/${target}`);
                }
              },
              onNodeDragStart: () => {
                // Tell DirectionalConnectors to hide its dots — otherwise
                // the 20px hit-boxes fight the node-drag gesture.
                useUiStore.getState().setIsDraggingNode(true);
              },
              onNodeDrag,
              onNodeDragStop: (_event, node) => {
                // Clear the connector-overlay drag flag first thing so a
                // bail-out anywhere below still re-enables the dots.
                useUiStore.getState().setIsDraggingNode(false);
                // Commit the post-drag position both locally (instant) and to
                // the server (eventually consistent via SSE echo, idempotent
                // by event id). Convert ReactFlow's parent-relative
                // `node.position` back to absolute flow coords before saving:
                // store is always absolute, ReactFlow is parent-relative when
                // `parentId` is set.
                const id = node.id;
                const off = ancestorOffset(id, useCanvasStore.getState().nodes);
                const x = node.position.x + off.x;
                const y = node.position.y + off.y;
                useCanvasStore.setState((state) => {
                  const existing = state.nodes[id];
                  if (!existing) return state;
                  return {
                    ...state,
                    nodes: { ...state.nodes, [id]: { ...existing, x, y } },
                  };
                });
                canvases.patchNode(slug, id, { x, y }).catch(() => {
                  // Network failure: the next snapshot/patch will reconcile.
                });
                // Area drop-target handling — consume + clear the in-flight
                // hover id, then persist the reparent if it actually changes.
                // The backend HTTP/MCP/CLI patch route detects a `parent`
                // field and dispatches `reparent_node`, which emits a
                // `NodeReparented` event; SSE echoes update the canonical
                // canvas state on every connected client.
                if (node.type !== "area") {
                  const target = useUiStore.getState().dropTargetAreaId;
                  useUiStore.getState().setDropTargetAreaId(null);
                  const existing = useCanvasStore.getState().nodes[id];
                  const currentParent = existing?.parent ?? null;
                  if (target && target !== currentParent && target !== id) {
                    // Optimistic local mirror so the nesting renders before
                    // the SSE echo arrives.
                    useCanvasStore.setState((state) => {
                      const cur = state.nodes[id];
                      if (!cur) return state;
                      return {
                        ...state,
                        nodes: { ...state.nodes, [id]: { ...cur, parent: target } },
                      };
                    });
                    canvases.patchNode(slug, id, { parent: target }).catch(() => {
                      // SSE reconciles.
                    });
                  } else if (!target && currentParent) {
                    // Dragged out of the parent. Unparent.
                    useCanvasStore.setState((state) => {
                      const cur = state.nodes[id];
                      if (!cur) return state;
                      return {
                        ...state,
                        nodes: { ...state.nodes, [id]: { ...cur, parent: null } },
                      };
                    });
                    canvases.patchNode(slug, id, { parent: null }).catch(() => {
                      // SSE reconciles.
                    });
                  }
                }
              },
              onSelectionDragStart: () => {
                useUiStore.getState().setIsDraggingNode(true);
              },
              onSelectionDragStop: (_event, draggedNodes) => {
                useUiStore.getState().setIsDraggingNode(false);
                // Multi-select drag: ReactFlow moves every selected node
                // visually during the gesture, but `onNodeDragStop` only
                // fires for the primary. Persist each. Convert each one's
                // parent-relative `node.position` back to absolute before
                // saving (mirrors single-drag).
                useCanvasStore.setState((state) => {
                  const next = { ...state.nodes };
                  for (const n of draggedNodes) {
                    const cur = next[n.id];
                    if (!cur) continue;
                    const off = ancestorOffset(n.id, next);
                    next[n.id] = { ...cur, x: n.position.x + off.x, y: n.position.y + off.y };
                  }
                  return { ...state, nodes: next };
                });
                for (const n of draggedNodes) {
                  const off = ancestorOffset(n.id, useCanvasStore.getState().nodes);
                  canvases
                    .patchNode(slug, n.id, { x: n.position.x + off.x, y: n.position.y + off.y })
                    .catch(() => {
                      // SSE reconciles next snapshot.
                    });
                }
              },
            })}
      >
        <Background />
        <Controls showInteractive={!readOnly} />
        <MiniMap pannable zoomable />
      </ReactFlow>
      <UploadJobsOverlay jobs={uploadJobs} />
      {/* Mini-toolbar above the selection and the right-click context menu.
          Hidden in readOnly canvases (snapshotter, monitor route). Both
          read selection from ReactFlow's per-node `selected` flag via
          xyflow's useStore. */}
      {readOnly ? null : (
        <>
          <NodeContextToolbar workspaceSlug={slug} />
          <NodeContextMenu
            workspaceSlug={slug}
            target={contextMenuTarget}
            onClose={() => setContextMenuTarget(null)}
          />
          {/* Miro-style edge editor — floating mini-toolbar at the
              selected edge's midpoint, the right-click context menu, and
              the waypoint drag overlay (only for smooth/step/straight
              routings). Each is no-op when there's no selected edge. */}
          <EdgeContextToolbar workspaceSlug={slug} />
          <EdgeContextMenu
            workspaceSlug={slug}
            target={edgeContextTarget}
            onClose={() => setEdgeContextTarget(null)}
          />
          <WaypointEditor workspaceSlug={slug} />
          {/* WYSIWYG paint preview. Only renders while the user is
              actively drag-sizing an armed shape; `pointer-events-none`
              so the gesture's pointer-up still reaches our wrapper. */}
          <PaintGhost rect={paintRect} nodeType={armedTool} />
        </>
      )}
    </div>
  );
}
