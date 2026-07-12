import {
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge as RfEdge,
  type EdgeChange,
  type Node as RfNode,
  type NodeChange,
} from "@xyflow/react";
import { useCallback, useEffect, useState } from "react";

import { canvases } from "@/api/canvases";
import { projectCanvasEdges, projectCanvasNode } from "@/canvas/canvasProjection";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

type CanvasFlowState = {
  rfNodes: RfNode[];
  rfEdges: RfEdge[];
  onNodesChange: (changes: NodeChange<RfNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<RfEdge>[]) => void;
  onConnect: (connection: Connection) => void;
};

export function useCanvasFlowState(slug: string, readOnly: boolean): CanvasFlowState {
  const nodes = useCanvasStore((state) => state.nodes);
  const edges = useCanvasStore((state) => state.edges);
  const hoveredSourceRef = useUiStore((state) => state.hoveredSourceRef);
  const hoveredNodeId = useUiStore((state) => state.hoveredNodeId);
  const selectedEdgeId = useUiStore((state) => state.selectedEdgeId);
  const [rfNodes, setRfNodes] = useState<RfNode[]>([]);
  const [rfEdges, setRfEdges] = useState<RfEdge[]>([]);

  useEffect(() => {
    setRfNodes((previous) => {
      const wasSelected = new Set(previous.filter((node) => node.selected).map((node) => node.id));
      const pendingId = useUiStore.getState().pendingInlineRenameNodeId;
      const selected = pendingId ? new Set([pendingId]) : wasSelected;
      return Object.values(nodes).map((node) => ({
        ...projectCanvasNode(node, nodes),
        selected: selected.has(node.id),
      }));
    });
  }, [nodes]);

  useEffect(() => {
    setRfEdges(projectCanvasEdges(nodes, edges, {
      hoveredSourceRef,
      hoveredNodeId,
      selectedEdgeId,
    }));
  }, [edges, nodes, hoveredSourceRef, hoveredNodeId, selectedEdgeId]);

  const onNodesChange = useCallback((changes: NodeChange<RfNode>[]) => {
    setRfNodes((current) => applyNodeChanges(changes, current));
    if (readOnly) return;
    for (const change of changes) {
      if (change.type === "remove") {
        useCanvasStore.setState((state) => {
          if (!state.nodes[change.id]) return state;
          const { [change.id]: _removed, ...remaining } = state.nodes;
          return { ...state, nodes: remaining };
        });
        void canvases.removeNode(slug, change.id).catch(() => {
          // SSE reconciles a rejected optimistic delete.
        });
        continue;
      }
      if (change.type !== "dimensions" || change.resizing !== false || !change.dimensions) {
        continue;
      }
      const existing = useCanvasStore.getState().nodes[change.id];
      if (!existing) continue;
      const previousWidth = (existing.data?.width as number | undefined) ?? null;
      const previousHeight = (existing.data?.height as number | undefined) ?? null;
      if (
        previousWidth === change.dimensions.width
        && previousHeight === change.dimensions.height
      ) {
        continue;
      }
      const dimensions = change.dimensions;
      useCanvasStore.setState((state) => {
        const current = state.nodes[change.id];
        if (!current) return state;
        return {
          ...state,
          nodes: {
            ...state.nodes,
            [change.id]: {
              ...current,
              data: { ...current.data, width: dimensions.width, height: dimensions.height },
            },
          },
        };
      });
      void canvases.patchNode(slug, change.id, {
        data: {
          ...(existing.data ?? {}),
          width: dimensions.width,
          height: dimensions.height,
        },
      }).catch(() => {
        // SSE reconciles a rejected resize.
      });
    }
  }, [readOnly, slug]);

  const onEdgesChange = useCallback((changes: EdgeChange<RfEdge>[]) => {
    setRfEdges((current) => applyEdgeChanges(changes, current));
    if (readOnly) return;
    for (const change of changes) {
      if (change.type !== "remove") continue;
      useCanvasStore.setState((state) => {
        if (!state.edges[change.id]) return state;
        const { [change.id]: _removed, ...remaining } = state.edges;
        return { ...state, edges: remaining };
      });
      void canvases.removeEdge(slug, change.id).catch(() => {
        // SSE reconciles a rejected optimistic delete.
      });
    }
  }, [readOnly, slug]);

  const onConnect = useCallback((connection: Connection) => {
    if (readOnly) return;
    const { source, target, sourceHandle, targetHandle } = connection;
    if (!source || !target) return;
    const state = useCanvasStore.getState();
    const sourceNode = state.nodes[source];
    const targetNode = state.nodes[target];
    if (!sourceNode || !targetNode) return;

    if (
      sourceHandle?.startsWith("row:")
      && targetHandle?.startsWith("region:")
      && targetNode.node_type === "document"
    ) {
      const regionId = targetHandle.slice("region:".length);
      const rowData = sourceNode.data as {
        source_ref?: { page?: number; bbox?: number[] };
        rows?: Array<{ key?: string; source_ref?: { page?: number; bbox?: number[] } }>;
      } | undefined;
      const rowIndex = Number(sourceHandle.split(":")[1] ?? "-1");
      const row = rowData?.rows?.[rowIndex];
      const page = row?.source_ref?.page ?? rowData?.source_ref?.page;
      const bbox = row?.source_ref?.bbox ?? rowData?.source_ref?.bbox;
      const targetData = targetNode.data as { slug?: string } | undefined;
      void canvases.addEdge(slug, {
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
      }).catch((error) => {
        console.error("row-to-region wire failed", error);
      });
      if (row && rowData?.rows && page !== undefined) {
        const rows = rowData.rows.map((item, index) => (
          index === rowIndex
            ? { ...item, source_ref: { page, region_id: regionId, bbox } }
            : item
        ));
        void canvases.patchNode(slug, source, { data: { ...rowData, rows } }).catch((error) => {
          console.error("row source_ref backfill failed", error);
        });
      }
      return;
    }

    void canvases.addEdge(slug, {
      source,
      target,
      ...(sourceHandle ? { sourceHandle } : {}),
      ...(targetHandle ? { targetHandle } : {}),
      edge_type: sourceHandle || targetHandle ? "anchored" : "floating",
    }).catch((error) => {
      console.error("generic connect failed", error);
    });
  }, [readOnly, slug]);

  return { rfNodes, rfEdges, onNodesChange, onEdgesChange, onConnect };
}
