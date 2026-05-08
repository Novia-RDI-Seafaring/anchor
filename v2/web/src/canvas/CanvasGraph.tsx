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
import { useCallback, useEffect, useState } from "react";

import { canvases } from "@/api/canvases";
import { AnchoredEdge } from "@/canvas/edges/AnchoredEdge";
import { EdgeMarkerDefs } from "@/canvas/edges/EdgeMarkerDefs";
import { FloatingEdge } from "@/canvas/edges/FloatingEdge";
import { nodeTypes } from "@/canvas/registry";
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
  // actually changed on the store side.
  useEffect(() => {
    setRfNodes(Object.values(nodes).map(toRfNode));
  }, [nodes]);

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
  }, []);

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

  // In readOnly mode the canvas becomes a pure projection: no drags, no
  // drops, no dblclick → viewer. It still subscribes to SSE so any state
  // change emitted by the rest of the system shows up live.
  return (
    <div
      className="relative h-full w-full"
      {...(readOnly ? {} : { onDragOver, onDrop })}
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
