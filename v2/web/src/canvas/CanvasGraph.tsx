import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Edge as RfEdge,
  type EdgeChange,
  type Node as RfNode,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { AnchoredEdge } from "@/canvas/edges/AnchoredEdge";
import { EdgeMarkerDefs } from "@/canvas/edges/EdgeMarkerDefs";
import { FloatingEdge } from "@/canvas/edges/FloatingEdge";
import { nodeTypes, paletteEntries } from "@/canvas/registry";
import { CanvasSse } from "@/realtime/sseClient";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

// Custom edge renderers keyed by the `edge_type` string the backend emits.
// `floating` = loose graph edge. `anchored` = handle-keyed (port → port,
// evidence row → bbox). The dispatcher inside each component switches on
// `data.marker` to pick arrowheads / dashing / labels — see
// `canvas/edges/markers.ts`.
const edgeTypes = { floating: FloatingEdge, anchored: AnchoredEdge };

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

type StoreNode = { id: string; node_type: string; label: string; x: number; y: number; data?: Record<string, unknown> };

function toRfNode(n: StoreNode): RfNode {
  // Areas render behind other nodes and don't trap pointer events on their
  // empty body — clicks pass through to whatever sits on top.
  const isArea = n.node_type === "area";
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { label: n.label, ...(n.data ?? {}) },
    type: n.node_type,
    ...(isArea ? { zIndex: -1, draggable: true, selectable: false } : {}),
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
  const setSelectedNodeId = useUiStore((s) => s.setSelectedNodeId);
  const setPropertiesOpen = useUiStore((s) => s.setPropertiesOpen);
  const armedTool = useUiStore((s) => s.armedTool);
  const disarmTool = useUiStore((s) => s.disarmTool);
  const selectedNodeId = useUiStore((s) => s.selectedNodeId);
  // Pointer-down origin for armed-tool drag-to-size. Lives in a ref so
  // pointermove/up handlers don't trigger re-renders on every pixel.
  const armDownRef = useRef<{ x: number; y: number; clientX: number; clientY: number } | null>(
    null,
  );

  // ReactFlow needs to own the per-frame drag position. We seed its internal
  // node list from the Zustand store and re-seed whenever the store changes
  // (snapshot, SSE patch, etc.). `onNodesChange` lets ReactFlow update its
  // own state during drag/select/etc.
  const [rfNodes, setRfNodes] = useState<RfNode[]>([]);
  const [rfEdges, setRfEdges] = useState<RfEdge[]>([]);

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
  // actually changed on the store side. The `selected` prop is stamped here
  // from `uiStore.selectedNodeId` so an external "deselect" (Esc, pane
  // click handler, properties-panel close) instantly clears the selection
  // ring + collapses the inline edit affordances.
  useEffect(() => {
    setRfNodes(
      Object.values(nodes).map((n) => ({
        ...toRfNode(n),
        selected: selectedNodeId === n.id,
      })),
    );
  }, [nodes, selectedNodeId]);

  useEffect(() => {
    setRfEdges(Object.values(edges).map((e) => {
      // Map backend edge_type → ReactFlow type. Unknown edge_type values
      // fall back to "floating" so they still render with the marker
      // dispatcher rather than the (undefined) default edge.
      const type = e.edge_type === "anchored" ? "anchored" : "floating";
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? undefined,
        targetHandle: e.targetHandle ?? undefined,
        label: e.label,
        type,
        data: { ...(e.data ?? {}), label: e.label || undefined },
      } satisfies RfEdge;
    }));
  }, [edges]);

  const onNodesChange = useCallback((changes: NodeChange<RfNode>[]) => {
    setRfNodes((curr) => applyNodeChanges(changes, curr));
    if (readOnly) return;
    for (const change of changes) {
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
  }, []);

  const onDragOver = useCallback((event: React.DragEvent) => {
    const types = event.dataTransfer.types;
    // Accept either OS files (PDFs etc.) or our shell's structured payloads.
    const accepted = types.includes("Files")
      || types.includes("application/x-anchor-node");
    if (!accepted) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const onDrop = useCallback(async (event: React.DragEvent) => {
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });

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
  // displacement. The threshold (4 px) matches a typical "wobble" — under
  // that we treat it as a click.
  const PLACE_DRAG_THRESHOLD_PX = 4;

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
    armDownRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
      ...screenToFlowPosition({ x: event.clientX, y: event.clientY }),
    };
  };

  const onPointerUp = (event: React.PointerEvent) => {
    if (!armedTool) return;
    const down = armDownRef.current;
    armDownRef.current = null;
    if (!down) return;
    const dx = event.clientX - down.clientX;
    const dy = event.clientY - down.clientY;
    const dist = Math.hypot(dx, dy);
    if (dist < PLACE_DRAG_THRESHOLD_PX) {
      // Single-click placement: default size at the click point.
      void placeArmedNode(down.x, down.y);
      return;
    }
    // Drag-to-size — only honoured for sizeable shapes. Cards fall back to
    // single-click placement at the start point.
    if (!CAN_SIZE[armedTool]) {
      void placeArmedNode(down.x, down.y);
      return;
    }
    const upFlow = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const minX = Math.min(down.x, upFlow.x);
    const minY = Math.min(down.y, upFlow.y);
    const width = Math.max(40, Math.abs(upFlow.x - down.x));
    const height = Math.max(24, Math.abs(upFlow.y - down.y));
    void placeArmedNode(minX, minY, { width, height });
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
        fitView
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
        zoomOnScroll
        panOnDrag
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
              onNodeClick: (_event, node) => { setSelectedNodeId(node.id); setPropertiesOpen(true); },
              onPaneClick: () => { setSelectedNodeId(null); setPropertiesOpen(false); },
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
                }
              },
              onNodeDragStop: (_event, node) => {
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
              },
            })}
      >
        <Background />
        <Controls showInteractive={!readOnly} />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}
