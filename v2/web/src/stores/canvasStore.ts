import { create } from "zustand";

import type { CanvasEvent } from "@/realtime/sseClient";

type Node = { id: string; node_type: string; label: string; x: number; y: number; data?: Record<string, unknown> };
type Edge = {
  id: string;
  source: string;
  target: string;
  label: string;
  edge_type: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  data?: Record<string, unknown>;
};

// Snapshot mirrors the wire shape from `GET /api/workspaces/{slug}/state`.
// Field types are loose dicts because the wire is JSON; the store narrows to
// `Node`/`Edge` on entry. Anything extra in the dict survives in `data`.
type WireRow = Record<string, unknown> & { id: string };

type Snapshot = {
  slug: string;
  title: string;
  version: number;
  nodes: WireRow[];
  edges: WireRow[];
  metadata: Record<string, unknown>;
};

function asNode(row: WireRow): Node {
  return {
    id: row.id,
    node_type: (row.node_type as string) ?? "concept",
    label: (row.label as string) ?? "",
    x: (row.x as number) ?? 0,
    y: (row.y as number) ?? 0,
    data: (row.data as Record<string, unknown>) ?? {},
  };
}

function asEdge(row: WireRow): Edge {
  return {
    id: row.id,
    source: row.source as string,
    target: row.target as string,
    label: (row.label as string) ?? "",
    edge_type: (row.edge_type as string) ?? "floating",
    sourceHandle: (row.sourceHandle as string | null | undefined)
      ?? (row.source_handle as string | null | undefined)
      ?? null,
    targetHandle: (row.targetHandle as string | null | undefined)
      ?? (row.target_handle as string | null | undefined)
      ?? null,
    data: (row.data as Record<string, unknown>) ?? {},
  };
}

export type Activity = {
  id: string;
  type: string;
  text: string;
  at: number;
};

function describeEvent(
  evt: CanvasEvent,
  prevNodes: Record<string, Node>,
  prevEdges: Record<string, Edge>,
): string {
  const p = evt.payload as Record<string, unknown>;
  const id = p.id as string | undefined;
  switch (evt.type) {
    case "NodeAdded": {
      const kind = (p.node_type as string) ?? "node";
      const label = (p.label as string) || (id ?? "");
      return `+ ${kind} "${label}"`;
    }
    case "NodeRemoved": {
      const n = id ? prevNodes[id] : undefined;
      return `− ${n?.node_type ?? "node"} "${n?.label ?? id ?? ""}"`;
    }
    case "NodeMoved": {
      const n = id ? prevNodes[id] : undefined;
      return `· moved ${n?.label ?? id ?? ""}`;
    }
    case "NodeResized":
      return `· resized ${id ?? ""}`;
    case "NodeReparented":
      return `· reparented ${id ?? ""}`;
    case "NodeUpdated": {
      const n = id ? prevNodes[id] : undefined;
      return `~ ${n?.label ?? id ?? ""}`;
    }
    case "EdgeAdded":
      return `+ edge ${(p.source as string) ?? "?"} → ${(p.target as string) ?? "?"}`;
    case "EdgeRemoved": {
      const e = id ? prevEdges[id] : undefined;
      return `− edge ${e?.source ?? "?"} → ${e?.target ?? "?"}`;
    }
    case "CanvasCleared":
      return "cleared canvas";
    default:
      return evt.type;
  }
}

type State = {
  slug: string | null;
  version: number;
  nodes: Record<string, Node>;
  edges: Record<string, Edge>;
  activity: Activity[];
  setSnapshot: (snap: Snapshot) => void;
  applyEvent: (evt: CanvasEvent) => void;
  reset: () => void;
};

export const useCanvasStore = create<State>((set) => ({
  slug: null,
  version: 0,
  nodes: {},
  edges: {},
  activity: [],
  setSnapshot: (snap) => set({
    slug: snap.slug,
    version: snap.version,
    nodes: Object.fromEntries(snap.nodes.map((row) => {
      const n = asNode(row);
      return [n.id, n];
    })),
    edges: Object.fromEntries(snap.edges.map((row) => {
      const e = asEdge(row);
      return [e.id, e];
    })),
    activity: [],
  }),
  applyEvent: (evt) => set((state) => {
    if (state.version >= evt.version) return state;
    const text = describeEvent(evt, state.nodes, state.edges);
    const nodes = { ...state.nodes };
    const edges = { ...state.edges };
    const p = evt.payload as Record<string, unknown>;
    switch (evt.type) {
      case "NodeAdded":
        nodes[p.id as string] = {
          id: p.id as string,
          node_type: (p.node_type as string) ?? "concept",
          label: (p.label as string) ?? "",
          x: (p.x as number) ?? 0,
          y: (p.y as number) ?? 0,
          data: (p.data as Record<string, unknown>) ?? {},
        };
        break;
      case "NodeRemoved":
        delete nodes[p.id as string];
        break;
      case "NodeMoved": {
        const id = p.id as string;
        if (nodes[id]) nodes[id] = { ...nodes[id], x: p.x as number, y: p.y as number };
        break;
      }
      case "NodeResized": {
        const id = p.id as string;
        if (nodes[id]) nodes[id] = { ...nodes[id], ...(p as object) };
        break;
      }
      case "NodeReparented": {
        const id = p.id as string;
        if (nodes[id]) nodes[id] = { ...nodes[id], data: { ...nodes[id].data, parent: p.parent } };
        break;
      }
      case "NodeUpdated": {
        const id = p.id as string;
        if (nodes[id]) {
          nodes[id] = { ...nodes[id], ...(p.fields as Record<string, unknown>) };
        }
        break;
      }
      case "EdgeAdded":
        edges[p.id as string] = {
          id: p.id as string,
          source: p.source as string,
          target: p.target as string,
          label: (p.label as string) ?? "",
          edge_type: (p.edge_type as string) ?? "floating",
          sourceHandle: (p.sourceHandle as string | null | undefined)
            ?? (p.source_handle as string | null | undefined)
            ?? null,
          targetHandle: (p.targetHandle as string | null | undefined)
            ?? (p.target_handle as string | null | undefined)
            ?? null,
          data: (p.data as Record<string, unknown>) ?? {},
        };
        break;
      case "EdgeRemoved":
        delete edges[p.id as string];
        break;
      case "CanvasCleared":
        return {
          ...state,
          nodes: {},
          edges: {},
          version: evt.version,
          activity: [
            { id: evt.id, type: evt.type, text, at: Date.now() },
            ...state.activity,
          ].slice(0, 8),
        };
    }
    return {
      ...state,
      nodes,
      edges,
      version: evt.version,
      activity: [
        { id: evt.id, type: evt.type, text, at: Date.now() },
        ...state.activity,
      ].slice(0, 8),
    };
  }),
  reset: () => set({ slug: null, version: 0, nodes: {}, edges: {}, activity: [] }),
}));
