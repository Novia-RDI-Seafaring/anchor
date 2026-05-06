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
import { nodeTypes } from "@/canvas/registry";
import { CanvasSse } from "@/realtime/sseClient";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

type Props = { slug: string };

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

export function CanvasGraph({ slug }: Props) {
  return (
    <ReactFlowProvider>
      <CanvasGraphInner slug={slug} />
    </ReactFlowProvider>
  );
}

function CanvasGraphInner({ slug }: Props) {
  const setSnapshot = useCanvasStore((s) => s.setSnapshot);
  const applyEvent = useCanvasStore((s) => s.applyEvent);
  const reset = useCanvasStore((s) => s.reset);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const { screenToFlowPosition } = useReactFlow();
  const openPdf = useUiStore((s) => s.openPdf);

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
    setRfEdges(Object.values(edges).map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      type: "default",
    })));
  }, [edges]);

  const onNodesChange = useCallback((changes: NodeChange<RfNode>[]) => {
    setRfNodes((curr) => applyNodeChanges(changes, curr));
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange<RfEdge>[]) => {
    setRfEdges((curr) => applyEdgeChanges(changes, curr));
  }, []);

  const onDragOver = useCallback((event: React.DragEvent) => {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }, []);

  const onDrop = useCallback(async (event: React.DragEvent) => {
    if (!event.dataTransfer.files?.length) return;
    event.preventDefault();
    const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    for (const file of Array.from(event.dataTransfer.files)) {
      if (!file.name.toLowerCase().endsWith(".pdf")) continue;
      try {
        await canvases.uploadFile(slug, file, flowPos.x, flowPos.y);
        // Placeholder document node arrives via SSE; status will update as
        // the pipeline progresses (pending → ingesting → ready).
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("upload failed", err);
      }
    }
  }, [slug, screenToFlowPosition]);

  return (
    <div className="h-full w-full" onDragOver={onDragOver} onDrop={onDrop}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        onNodeDoubleClick={(_event, node) => {
          // Document nodes that are ready open the PDF viewer.
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
        }}
        onNodeDragStop={(_event, node) => {
          // Commit the post-drag position both locally (instant) and to the
          // server (eventually consistent via SSE echo, idempotent by event id).
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
        }}
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}
