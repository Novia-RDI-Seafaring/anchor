import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge as RfEdge,
  type EdgeChange,
  type Node as RfNode,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { breadcrumb } from "@/canvas/breadcrumb";
import { AnchoredEdge } from "@/canvas/edges/AnchoredEdge";
import { EdgeMarkerDefs } from "@/canvas/edges/EdgeMarkerDefs";
import { FloatingEdge } from "@/canvas/edges/FloatingEdge";
import { SmoothEdge, StepEdge, StraightEdge } from "@/canvas/edges/RoutedEdge";
import { pickEdgeMode } from "@/canvas/edges/edge-mode";
import { EdgeContextMenu, type EdgeContextMenuTarget } from "@/canvas/EdgeContextMenu";
import { EdgeContextToolbar } from "@/canvas/EdgeContextToolbar";
import { NodeContextMenu, type ContextMenuTarget } from "@/canvas/NodeContextMenu";
import { NodeContextToolbar } from "@/canvas/NodeContextToolbar";
import { WaypointEditor } from "@/canvas/WaypointEditor";
import {
  PAINT_DRAG_THRESHOLD_PX,
  PaintGhost,
  type PaintRect,
  ghostIsSquare,
  maybeSquareRect,
  paintRectFrom,
} from "@/canvas/PaintGhost";
import { nodeTypes, paletteEntries } from "@/canvas/registry";
import { CanvasSse } from "@/realtime/sseClient";
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

type StoreNode = {
  id: string;
  node_type: string;
  label: string;
  x: number;
  y: number;
  /** Backend `Node.parent` — id of the container node (e.g. an Area) this
   *  node is nested inside, or null/undefined when free-floating. */
  parent?: string | null;
  data?: Record<string, unknown>;
};

/**
 * Tiny 8-char base36 id — used to seed unique child-canvas slugs when a
 * user drops a sub-canvas tile. Collision-safe enough for human-driven
 * canvas creation (the server's `create` is idempotent on slug anyway).
 */
function shortId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function toRfNode(n: StoreNode, allNodes: Record<string, StoreNode>): RfNode {
  // Areas render behind other nodes (zIndex: -1) so the empty interior
  // doesn't trap clicks meant for whatever sits on top. `selectable: true`
  // still lets the user click the dashed border or header to select the
  // area itself (and resize it via NodeResizer); clicks on the transparent
  // interior fall through to the nodes inside.
  const isArea = n.node_type === "area";
  // Parent/child wiring — when this node has a `parent` AND that parent
  // node currently exists, hand ReactFlow the standard `parentId` +
  // `extent: "parent"` pair. ReactFlow then:
  //   - moves the child along when the parent (Area) is dragged,
  //   - clamps the child's position inside the parent's bounds,
  //   - converts the position to parent-relative coordinates internally.
  // Defensive: a `parent` that points at a missing node is silently
  // ignored (otherwise ReactFlow logs a warning every render).
  const parentExists = n.parent != null && allNodes[n.parent] != null;
  const parentProps = parentExists
    ? ({ parentId: n.parent as string, extent: "parent" as const })
    : {};
  // Lock support: `data.locked === true` freezes the node in place
  // (ReactFlow's `draggable: false`) and the shape primitives skip
  // mounting NodeResizer when the prop is read at render time. The flag
  // is forward-compatible: producers / consumers can ignore it today.
  const locked = (n.data as { locked?: boolean } | undefined)?.locked === true;
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { label: n.label, ...(n.data ?? {}) },
    type: n.node_type,
    ...parentProps,
    ...(isArea ? { zIndex: -1, draggable: true } : {}),
    ...(locked ? { draggable: false } : {}),
  };
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

function CanvasGraphInner({ slug, readOnly }: Props) {
  const setSnapshot = useCanvasStore((s) => s.setSnapshot);
  const applyEvent = useCanvasStore((s) => s.applyEvent);
  const reset = useCanvasStore((s) => s.reset);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const { screenToFlowPosition } = useReactFlow();
  const openPdf = useUiStore((s) => s.openPdf);
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
  // Drives the floating↔anchored swap on evidence edges. When something
  // broadcasts a hovered source_ref (spec-row hover, region hover, an edge
  // hover that reflects back) the matching evidence edge flips from
  // node-to-node float to row-handle→region-handle anchored.
  const hoveredSourceRef = useUiStore((s) => s.hoveredSourceRef);
  const setSelectedNodeId = useUiStore((s) => s.setSelectedNodeId);
  const setSelectedEdgeId = useUiStore((s) => s.setSelectedEdgeId);
  const selectedEdgeId = useUiStore((s) => s.selectedEdgeId);
  const setPropertiesOpen = useUiStore((s) => s.setPropertiesOpen);
  const armedTool = useUiStore((s) => s.armedTool);
  const disarmTool = useUiStore((s) => s.disarmTool);
  const navigate = useNavigate();
  // Pointer-down origin for armed-tool drag-to-size. Lives in a ref so
  // pointermove handlers can update the in-flight ghost rect without
  // re-rendering ReactFlow on every pixel — only the ghost state below
  // does that, and only when the rect actually changes.
  const armDownRef = useRef<{ clientX: number; clientY: number } | null>(null);
  // Screen-space rect for the WYSIWYG ghost preview while drag-to-size is
  // in progress. `null` when not painting. The ghost outline mirrors the
  // armed tool's silhouette via `PaintGhost` so the user sees exactly the
  // shape they're about to drop.
  const [paintRect, setPaintRect] = useState<PaintRect | null>(null);

  // ReactFlow needs to own the per-frame drag position. We seed its internal
  // node list from the Zustand store and re-seed whenever the store changes
  // (snapshot, SSE patch, etc.). `onNodesChange` lets ReactFlow update its
  // own state during drag/select/etc.
  const [rfNodes, setRfNodes] = useState<RfNode[]>([]);
  const [rfEdges, setRfEdges] = useState<RfEdge[]>([]);
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
      onPatch: applyEvent,
    });
    sse.connect();
    return () => {
      cancelled = true;
      sse.disconnect();
    };
  }, [slug, applyEvent, reset, setSnapshot]);

  // Reflect store → ReactFlow. Only updates when the store reference changes;
  // ReactFlow's internal drag state isn't disturbed unless a relevant node
  // actually changed on the store side. Multi-selection (Shift+click) is
  // owned by ReactFlow itself — we preserve the prior `selected` flag on
  // each node when rebuilding from the store so the per-node selection
  // ring sticks across SSE patches. `selectedNodeId` is only used to scope
  // single-node ops like the right-side Properties Panel; it no longer
  // overrides the per-node selected flag (which would clobber multi-select).
  useEffect(() => {
    setRfNodes((prev) => {
      const wasSelected = new Set(prev.filter((n) => n.selected).map((n) => n.id));
      // Pass the full node map so `toRfNode` can resolve `parent` → `parentId`
      // only when the parent actually exists in this snapshot.
      return Object.values(nodes).map((n) => ({
        ...toRfNode(n, nodes),
        selected: wasSelected.has(n.id),
      }));
    });
  }, [nodes]);

  useEffect(() => {
    // pickEdgeMode resolves every edge to its ReactFlow renderer type. For
    // non-evidence edges that's just the stored `edge_type` (now one of
    // floating / anchored / smooth / step / straight). For evidence edges
    // it implements the row-hover swap: when the active source_ref matches
    // the edge's stored ref, flip to `anchored` so the handle wiring shows
    // — regardless of whether the user previously picked smooth/step/etc.
    //
    // A second pass dims the OTHER evidence edges of the same target doc
    // so the active row→region link visually pops.
    const typePicks: Record<string, string> = {};
    const evidenceForDoc: Record<string, string[]> = {};
    let activeEdgeId: string | null = null;

    for (const e of Object.values(edges)) {
      const tgt = nodes[e.target];
      const tgtSlug = (tgt?.data as { slug?: string } | undefined)?.slug;
      const mode = pickEdgeMode(
        {
          edge_type: e.edge_type,
          data: e.data as { kind?: string; source_ref?: Record<string, unknown> } | undefined,
          targetDocSlug: tgtSlug,
        },
        hoveredSourceRef,
      );
      typePicks[e.id] = mode;
      if (e.data?.kind === "evidence") {
        if (tgtSlug) (evidenceForDoc[tgtSlug] ??= []).push(e.id);
        if (mode === "anchored") activeEdgeId = e.id;
      }
    }
    // Sibling-fade: when ANY evidence edge is active, dim the others
    // pointing at the same document. The active edge stays bright.
    const dimmedEvidence = new Set<string>();
    if (activeEdgeId && hoveredSourceRef?.slug) {
      for (const eid of evidenceForDoc[hoveredSourceRef.slug] ?? []) {
        if (eid !== activeEdgeId) dimmedEvidence.add(eid);
      }
    }

    setRfEdges(Object.values(edges).map((e) => {
      const type = typePicks[e.id] ?? "floating";
      const dimmed = dimmedEvidence.has(e.id);
      const isSelected = selectedEdgeId === e.id;
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? undefined,
        targetHandle: e.targetHandle ?? undefined,
        label: e.label,
        type,
        data: { ...(e.data ?? {}), label: e.label || undefined },
        style: dimmed ? { opacity: 0.3 } : undefined,
        selected: isSelected,
      } satisfies RfEdge;
    }));
  }, [edges, nodes, hoveredSourceRef, selectedEdgeId]);

  const onNodesChange = useCallback((changes: NodeChange<RfNode>[]) => {
    setRfNodes((curr) => applyNodeChanges(changes, curr));
    if (readOnly) return;
    for (const change of changes) {
      // Backspace / Delete fires `remove` changes. Without persisting,
      // the optimistic-only delete gets undone the moment the store →
      // rfNodes effect re-runs (because the store still has the node).
      if (change.type === "remove") {
        // Drop locally first so the UI doesn't flicker, then ask the
        // server. SSE will deliver the canonical NodeRemoved (+ cascade
        // EdgeRemoved); the store's version-monotonic applyEvent makes
        // the echo a no-op.
        useCanvasStore.setState((state) => {
          if (!state.nodes[change.id]) return state;
          const { [change.id]: _gone, ...rest } = state.nodes;
          return { ...state, nodes: rest };
        });
        canvases.removeNode(slug, change.id).catch(() => {
          // SSE will reconcile if the server rejected the delete.
        });
        continue;
      }
      if (change.type !== "dimensions") continue;
      // ReactFlow emits `dimensions` changes in three flavours:
      //   - `resizing: true`  → mid-drag; ignore (would hammer the API)
      //   - `resizing: false` → end-of-drag; persist
      //   - `resizing: undefined` → DOM measurement on mount or content
      //     change; NOT a user resize. We must skip these or we get an
      //     infinite loop: measurement → patch → SSE echo → store update
      //     → remount → measurement.
      if (change.resizing !== false) continue;
      const dim = change.dimensions;
      if (!dim) continue;
      // Skip the patch if the dimensions match the existing store value
      // (defensive — covers any non-user-initiated dimension events that
      // slipped through and any SSE reconciliation re-firing).
      const existing = useCanvasStore.getState().nodes[change.id];
      if (!existing) continue;
      const prevW = (existing.data?.width as number | undefined) ?? null;
      const prevH = (existing.data?.height as number | undefined) ?? null;
      if (prevW === dim.width && prevH === dim.height) continue;
      // Mirror locally so the store-driven re-render keeps the new size.
      useCanvasStore.setState((state) => {
        const cur = state.nodes[change.id];
        if (!cur) return state;
        return {
          ...state,
          nodes: {
            ...state.nodes,
            [change.id]: {
              ...cur,
              data: { ...cur.data, width: dim.width, height: dim.height },
            },
          },
        };
      });
      // Merge with existing data so the server's whole-data replace
      // doesn't wipe label-adjacent fields (body, tags, source_ref, …).
      canvases
        .patchNode(slug, change.id, {
          data: { ...(existing.data ?? {}), width: dim.width, height: dim.height },
        })
        .catch(() => {
          // SSE will reconcile.
        });
    }
  }, [readOnly, slug]);

  const onEdgesChange = useCallback((changes: EdgeChange<RfEdge>[]) => {
    setRfEdges((curr) => applyEdgeChanges(changes, curr));
    if (readOnly) return;
    for (const change of changes) {
      // Same fix as nodes: Backspace/Delete fires `remove`; persist it
      // or SSE re-syncs the edge back onto the canvas seconds later.
      if (change.type !== "remove") continue;
      useCanvasStore.setState((state) => {
        if (!state.edges[change.id]) return state;
        const { [change.id]: _gone, ...rest } = state.edges;
        return { ...state, edges: rest };
      });
      canvases.removeEdge(slug, change.id).catch(() => {
        // SSE will reconcile if the server rejected.
      });
    }
  }, [readOnly, slug]);

  /**
   * ReactFlow fires `onConnect` when the user finishes a connect drag — for
   * us, dragging from a spec-row handle (id="row:i:key") onto a document-
   * region handle (id="region:rid"). When both ends carry the row/region
   * naming convention, we materialise an anchored evidence edge AND patch
   * the spec row's source_ref to embed the region_id, so the row+edge stay
   * in sync (the row already knows the page+bbox; we just attach the
   * region).
   */
  const onConnect = useCallback((conn: Connection) => {
    if (readOnly) return;
    const { source, target, sourceHandle, targetHandle } = conn;
    if (!source || !target) return;
    const isRow = sourceHandle?.startsWith("row:");
    const isRegion = targetHandle?.startsWith("region:");
    const state = useCanvasStore.getState();
    const sourceNode = state.nodes[source];
    const targetNode = state.nodes[target];
    if (!sourceNode || !targetNode) return;

    if (isRow && isRegion && targetNode.node_type === "document") {
      // Row → region: build the full evidence-edge payload from the row's
      // existing source_ref, falling back to the spec's node-level ref.
      const regionId = targetHandle!.slice("region:".length);
      const rowData = sourceNode.data as {
        source_doc_slug?: string;
        source_ref?: { page?: number; bbox?: number[] };
        rows?: Array<{ key?: string; source_ref?: { page?: number; bbox?: number[] } }>;
      } | undefined;
      // Parse "row:<i>:<key>"  — index is authoritative since keys can repeat.
      const parts = sourceHandle!.split(":");
      const rowIndex = Number(parts[1] ?? "-1");
      const row = rowData?.rows?.[rowIndex];
      const page = row?.source_ref?.page ?? rowData?.source_ref?.page;
      const bbox = row?.source_ref?.bbox ?? rowData?.source_ref?.bbox;
      const targetData = targetNode.data as { slug?: string } | undefined;
      void canvases
        .addEdge(slug, {
          source,
          target,
          edge_type: "anchored",
          sourceHandle,
          targetHandle,
          data: {
            kind: "evidence",
            ...(targetData?.slug ? { source_doc_slug: targetData.slug } : {}),
            source_region_id: regionId,
            ...(page !== undefined ? {
              source_ref: { kind: "pdf-page-bbox", page, region_id: regionId, bbox },
            } : {}),
          },
        })
        .catch((err) => {
          // eslint-disable-next-line no-console
          console.error("row→region wire failed", err);
        });
      // Patch the row in the spec so its source_ref carries the region_id
      // — the data and the edge stay in lock-step (without this, the row
      // is wired visually but its provenance dict still says "no region").
      if (row && rowData?.rows && page !== undefined) {
        const draftRows = rowData.rows.map((r, i) => {
          if (i !== rowIndex) return r;
          return {
            ...r,
            source_ref: { page, region_id: regionId, bbox },
          };
        });
        void canvases
          .patchNode(slug, source, { data: { ...rowData, rows: draftRows } })
          .catch((err) => {
            // eslint-disable-next-line no-console
            console.error("row source_ref backfill failed", err);
          });
      }
      return;
    }

    // Generic floating edge for any other manual connect drag (e.g. two
    // plain nodes). Keep parity with the existing UX — drag = connect.
    void canvases
      .addEdge(slug, {
        source,
        target,
        ...(sourceHandle ? { sourceHandle } : {}),
        ...(targetHandle ? { targetHandle } : {}),
        edge_type: sourceHandle || targetHandle ? "anchored" : "floating",
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error("generic connect failed", err);
      });
  }, [readOnly, slug]);

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
        const w = (n.data?.width as number | undefined) ?? 320;
        const h = (n.data?.height as number | undefined) ?? 200;
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

  const onDragOver = useCallback((event: React.DragEvent) => {
    const types = event.dataTransfer.types;
    // Accept either OS files (PDFs etc.) or our shell's structured payloads.
    const accepted = types.includes("Files")
      || types.includes("application/x-anchor-node")
      || types.includes("application/x-anchor-canvas-link");
    if (!accepted) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const onDrop = useCallback(async (event: React.DragEvent) => {
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });

    // Path 0 — existing-canvas link: the Canvases tab in the Library
    // drawer emits this. Attach the dragged workspace as a sub-canvas
    // tile (no child workspace is created — this is a pure link).
    const linkRaw = event.dataTransfer.getData("application/x-anchor-canvas-link");
    if (linkRaw) {
      event.preventDefault();
      try {
        const { slug: linkedSlug, title } = JSON.parse(linkRaw) as {
          slug: string;
          title: string;
        };
        if (linkedSlug && linkedSlug !== slug) {
          await canvases.addNode(slug, {
            node_type: "canvas",
            label: title || linkedSlug,
            x: flowPos.x,
            y: flowPos.y,
            data: { canvas_slug: linkedSlug, title: title || linkedSlug },
          });
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("canvas-link drop failed", err);
      }
      return;
    }

    // Path 1 — shell payload: Palette or Library dragged a node spec onto the canvas.
    const nodeSpecRaw = event.dataTransfer.getData("application/x-anchor-node");
    if (nodeSpecRaw) {
      event.preventDefault();
      try {
        const spec = JSON.parse(nodeSpecRaw) as {
          node_type: string;
          label?: string;
          width?: number;
          height?: number;
          data?: Record<string, unknown>;
        };

        // Special path for sub-canvas tiles: the LeftToolRail tags the
        // payload with `__create_sub_canvas`. We provision a fresh child
        // workspace + drop the linking node atomically via the composite
        // `createSubCanvas` endpoint instead of the regular addNode path.
        if (spec.data?.__create_sub_canvas) {
          const subSlug = `${slug}-sub-${shortId()}`;
          const title = (spec.data?.title as string | undefined) ?? spec.label ?? "Sub-canvas";
          try {
            await canvases.createSubCanvas(slug, {
              slug: subSlug,
              title,
              x: flowPos.x,
              y: flowPos.y,
            });
          } catch (err) {
            // eslint-disable-next-line no-console
            console.error("sub-canvas creation failed", err);
          }
          return;
        }

        const res = (await canvases.addNode(slug, {
          ...spec,
          x: flowPos.x,
          y: flowPos.y,
        })) as { event?: { payload?: { id?: string } } } | null;
        const newId = res?.event?.payload?.id;

        // Evidence edge: if the dropped payload carries a source_doc_node_id
        // (e.g. dragging a region out of a document node), connect the new
        // node back to its source. The edge keeps the source_ref so it can
        // drive the cross-component hover-flip behavior.
        const data = spec.data ?? {};
        const sourceNodeId = (data.source_doc_node_id as string | undefined) ?? null;
        const sourceRef = data.source_ref as Record<string, unknown> | undefined;
        if (newId && sourceNodeId) {
          await canvases.addEdge(slug, {
            source: newId,
            target: sourceNodeId,
            edge_type: "anchored",
            data: {
              kind: "evidence",
              ...(sourceRef ? { source_ref: sourceRef } : {}),
              ...(data.source_region_id ? { source_region_id: data.source_region_id } : {}),
            },
          });
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("shell drop failed", err);
      }
      return;
    }

    // Path 2 — OS files: drop-to-ingest for PDFs.
    if (event.dataTransfer.files?.length) {
      event.preventDefault();
      for (const file of Array.from(event.dataTransfer.files)) {
        if (!file.name.toLowerCase().endsWith(".pdf")) continue;
        try {
          await canvases.uploadFile(slug, file, flowPos.x, flowPos.y);
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error("upload failed", err);
        }
      }
    }
  }, [slug, screenToFlowPosition]);

  // Armed-tool placement gesture. When `armedTool` is set, a click on the
  // pane places the shape at default size; a click-and-drag places it with
  // the dragged rect as its position+size.
  //
  // We listen on the wrapper div rather than ReactFlow's `onPaneClick` so
  // we can distinguish click from drag by comparing pointerdown→pointerup
  // displacement. The 4-px threshold lives in `PaintGhost` (shared with
  // the ghost-rect math) so the click-vs-drag boundary stays in lock-step.

  // Cards don't drag-to-size (their layout is content-driven beyond a
  // sensible default). Shapes (concept/entity/funnel/area) can grow.
  const CAN_SIZE: Record<string, boolean> = {
    concept: true,
    entity: true,
    funnel: true,
    area: true,
  };

  const placeArmedNode = async (
    flowX: number,
    flowY: number,
    sizeOverride?: { width: number; height: number },
  ) => {
    if (!armedTool) return;
    // Special path: sub-canvas placement goes through the composite
    // `createSubCanvas` endpoint so the child workspace + linking node
    // land atomically. The slug is generated client-side; the backend
    // returns the linking node id via SSE.
    if (armedTool === "canvas") {
      const subSlug = `${slug}-sub-${shortId()}`;
      try {
        await canvases.createSubCanvas(slug, {
          slug: subSlug,
          title: "Sub-canvas",
          x: flowX,
          y: flowY,
        });
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("armed sub-canvas placement failed", err);
      } finally {
        disarmTool();
      }
      return;
    }
    // Pull the palette meta for default size + payload shape.
    const all = [...paletteEntries("shapes"), ...paletteEntries("cards")];
    const meta = all.find((e) => e.name === armedTool)?.meta;
    const label = meta?.noDefaultLabel ? "" : meta?.label ?? "";
    const width = sizeOverride?.width ?? meta?.width;
    const height = sizeOverride?.height ?? meta?.height;
    try {
      await canvases.addNode(slug, {
        node_type: armedTool,
        label,
        x: flowX,
        y: flowY,
        ...(width !== undefined ? { width } : {}),
        ...(height !== undefined ? { height } : {}),
        data: { ...(meta?.data ?? {}), ...(width !== undefined ? { width } : {}), ...(height !== undefined ? { height } : {}) },
      });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("armed-tool placement failed", err);
    } finally {
      // Always disarm after placement; user can re-arm by clicking the
      // rail icon again.
      disarmTool();
    }
  };

  const onPointerDown = (event: React.PointerEvent) => {
    if (!armedTool) return;
    // Ignore clicks on existing nodes — the user might be trying to select
    // a node mid-arm. ReactFlow tags nodes with `.react-flow__node` so we
    // can sniff the event target.
    const target = event.target as HTMLElement;
    if (target.closest(".react-flow__node")) return;
    // Record screen-space origin only. Flow-space conversion happens at
    // pointer-up using the SAME endpoints the ghost rect uses, so the
    // WYSIWYG contract (ghost rect == dropped node rect) holds.
    armDownRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
    };
    setPaintRect(null);
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const down = armDownRef.current;
    if (!down || !armedTool) return;
    // Only sizeable shapes render the ghost — cards drop at default size
    // even when the user drags, so a ghost would be misleading.
    if (!CAN_SIZE[armedTool]) return;
    const raw = paintRectFrom(
      { x: down.clientX, y: down.clientY },
      { x: event.clientX, y: event.clientY },
    );
    const constrained = maybeSquareRect(
      raw,
      { x: down.clientX, y: down.clientY },
      ghostIsSquare(armedTool),
    );
    setPaintRect(constrained);
  };

  const onPointerUp = (event: React.PointerEvent) => {
    if (!armedTool) return;
    const down = armDownRef.current;
    armDownRef.current = null;
    setPaintRect(null);
    if (!down) return;
    const dx = event.clientX - down.clientX;
    const dy = event.clientY - down.clientY;
    const dist = Math.hypot(dx, dy);
    if (dist < PAINT_DRAG_THRESHOLD_PX) {
      // Single-click placement: default size at the click point. Convert
      // here (not at pointer-down) so we use exactly the same call site
      // every drop goes through — keeps the math consistent.
      const downFlow = screenToFlowPosition({ x: down.clientX, y: down.clientY });
      void placeArmedNode(downFlow.x, downFlow.y);
      return;
    }
    // Drag-to-size — only honoured for sizeable shapes. Cards fall back to
    // single-click placement at the start point.
    if (!CAN_SIZE[armedTool]) {
      const downFlow = screenToFlowPosition({ x: down.clientX, y: down.clientY });
      void placeArmedNode(downFlow.x, downFlow.y);
      return;
    }
    // WYSIWYG fix: compute the screen-space rect (same maths the ghost
    // showed), then convert THAT rect's two diagonal corners to flow space.
    // Sourcing both corners from the same `screenToFlowPosition` ensures
    // the drop lands at the ghost-shown rect for any zoom/pan/transform.
    // Square-locked (entity / circle) tools snap the rect to a square
    // anchored at the down corner — same constraint the ghost applies.
    const raw = paintRectFrom(
      { x: down.clientX, y: down.clientY },
      { x: event.clientX, y: event.clientY },
    );
    const screen = maybeSquareRect(
      raw,
      { x: down.clientX, y: down.clientY },
      ghostIsSquare(armedTool),
    );
    const topLeftFlow = screenToFlowPosition({ x: screen.left, y: screen.top });
    const bottomRightFlow = screenToFlowPosition({
      x: screen.left + screen.width,
      y: screen.top + screen.height,
    });
    const flowWidth = Math.max(40, Math.abs(bottomRightFlow.x - topLeftFlow.x));
    const flowHeight = Math.max(24, Math.abs(bottomRightFlow.y - topLeftFlow.y));
    void placeArmedNode(topLeftFlow.x, topLeftFlow.y, {
      width: flowWidth,
      height: flowHeight,
    });
  };

  // In readOnly mode the canvas becomes a pure projection: no drags, no
  // drops, no dblclick → viewer. It still subscribes to SSE so any state
  // change emitted by the rest of the system shows up live.
  return (
    <div
      className={`relative h-full w-full ${armedTool ? "cursor-crosshair" : ""}`}
      {...(readOnly
        ? {}
        : {
            onDragOver,
            onDrop,
            onPointerDown,
            onPointerMove,
            onPointerUp,
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
                // by event id).
                const id = node.id;
                const x = node.position.x;
                const y = node.position.y;
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
                // fires for the primary. Without persisting each one, the
                // rfNodes effect rebuilds from the store and the
                // non-primary nodes snap back to their pre-drag positions
                // — that's the "subtree rearranges after release" bug.
                useCanvasStore.setState((state) => {
                  const next = { ...state.nodes };
                  for (const n of draggedNodes) {
                    const cur = next[n.id];
                    if (!cur) continue;
                    next[n.id] = { ...cur, x: n.position.x, y: n.position.y };
                  }
                  return { ...state, nodes: next };
                });
                for (const n of draggedNodes) {
                  canvases
                    .patchNode(slug, n.id, { x: n.position.x, y: n.position.y })
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
