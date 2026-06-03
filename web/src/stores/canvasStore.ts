import { create } from "zustand";

import type { CanvasEvent } from "@/realtime/sseClient";

type Node = {
  id: string;
  node_type: string;
  label: string;
  x: number;
  y: number;
  /**
   * Parent node id (for area/container nesting). When set, ReactFlow
   * treats this node as a child of `parent` — moving the parent moves
   * the child, and the child's position becomes parent-relative.
   * Mirrors the backend `Node.parent` top-level field.
   */
  parent?: string | null;
  data?: Record<string, unknown>;
};
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

const INGEST_STAGE_LABELS: Record<string, string> = {
  silver_extract: "reading PDF",
  silver_polish: "polishing pages",
  gold_regions: "extracting gold data",
  embed: "embedding regions",
  silvered: "silver ready",
  gold_extracted: "gold data ready",
};

const INGEST_STAGE_RANGE: Record<string, { base: number; span: number }> = {
  silver_extract: { base: 5, span: 20 },
  silver_polish: { base: 25, span: 30 },
  gold_regions: { base: 55, span: 30 },
  embed: { base: 85, span: 10 },
};

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function stageProgress(stage: string, current: number, total: number): number {
  const range = INGEST_STAGE_RANGE[stage] ?? { base: 10, span: 80 };
  const fraction = total > 0 ? current / total : 0;
  return clampPercent(range.base + range.span * fraction);
}

function patchDocumentNodes(
  nodes: Record<string, Node>,
  docSlug: string,
  dataPatch: Record<string, unknown>,
): Record<string, Node> {
  let changed = false;
  const next = { ...nodes };
  for (const [id, node] of Object.entries(nodes)) {
    const data = node.data ?? {};
    if (node.node_type !== "document" || data.slug !== docSlug) continue;
    next[id] = {
      ...node,
      data: {
        ...data,
        ...dataPatch,
      },
    };
    changed = true;
  }
  return changed ? next : nodes;
}

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
    parent: (row.parent as string | null | undefined) ?? null,
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
    case "EdgeUpdated": {
      const e = id ? prevEdges[id] : undefined;
      return `~ edge ${e?.source ?? "?"} → ${e?.target ?? "?"}`;
    }
    case "CanvasCleared":
      return "cleared canvas";
    case "DocIngested":
      return `ingested ${p.slug as string}`;
    case "DocIngestFailed":
      return `ingest failed ${p.slug as string}`;
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
    if (evt.type === "IngestProgress") {
      const p = evt.payload as Record<string, unknown>;
      const docSlug = p.slug as string | undefined;
      if (!docSlug) return state;
      const stage = (p.stage as string | undefined) ?? "ingesting";
      const current = Number(p.current ?? 0);
      const total = Number(p.total ?? 0);
      const nodes = patchDocumentNodes(state.nodes, docSlug, {
        status: "ingesting",
        ingest_stage: stage,
        ingest_stage_label: INGEST_STAGE_LABELS[stage] ?? stage,
        ingest_current: current,
        ingest_total: total,
        ingest_progress: stageProgress(stage, current, total),
      });
      if (nodes === state.nodes) return state;
      return {
        ...state,
        nodes,
      };
    }
    if (evt.type === "DocSilvered") {
      const p = evt.payload as Record<string, unknown>;
      const docSlug = p.slug as string | undefined;
      if (!docSlug) return state;
      const nodes = patchDocumentNodes(state.nodes, docSlug, {
        status: "ingesting",
        page_count: p.page_count,
        ingest_stage: "silvered",
        ingest_stage_label: INGEST_STAGE_LABELS.silvered,
        ingest_progress: 35,
      });
      return nodes === state.nodes ? state : { ...state, nodes };
    }
    if (evt.type === "DocGoldExtracted") {
      const p = evt.payload as Record<string, unknown>;
      const docSlug = p.slug as string | undefined;
      if (!docSlug) return state;
      const nodes = patchDocumentNodes(state.nodes, docSlug, {
        status: "ingesting",
        region_count: p.region_count,
        ingest_stage: "gold_extracted",
        ingest_stage_label: INGEST_STAGE_LABELS.gold_extracted,
        ingest_progress: 90,
      });
      return nodes === state.nodes ? state : { ...state, nodes };
    }
    if (evt.type === "DocIngested") {
      const p = evt.payload as Record<string, unknown>;
      const docSlug = p.slug as string | undefined;
      if (!docSlug) return state;
      const summary = (p.summary as Record<string, unknown> | undefined) ?? {};
      const nodes = patchDocumentNodes(state.nodes, docSlug, {
        status: "ready",
        page_count: summary.page_count,
        region_count: summary.region_count,
        embedded_count: summary.embedded_count,
        ingest_stage: "complete",
        ingest_stage_label: "complete",
        ingest_progress: 100,
      });
      return nodes === state.nodes ? state : { ...state, nodes };
    }
    if (evt.type === "DocIngestFailed") {
      const p = evt.payload as Record<string, unknown>;
      const docSlug = p.slug as string | undefined;
      if (!docSlug) return state;
      const nodes = patchDocumentNodes(state.nodes, docSlug, {
        status: "failed",
        error: p.error,
        ingest_stage: p.stage,
        ingest_stage_label: "failed",
      });
      return nodes === state.nodes ? state : { ...state, nodes };
    }
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
          parent: (p.parent as string | null | undefined) ?? null,
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
        // `parent` is a top-level field on the canonical Node model
        // (mirrors backend reducer). Storing it on `data.parent` would
        // hide it from `toRfNode`'s `parent → parentId` mapping.
        if (nodes[id]) nodes[id] = { ...nodes[id], parent: (p.parent as string | null | undefined) ?? null };
        break;
      }
      case "NodeUpdated": {
        const id = p.id as string;
        if (nodes[id]) {
          const cur = nodes[id];
          const fields = (p.fields as Record<string, unknown>) ?? {};
          const known = new Set(["node_type", "label", "x", "y", "parent", "data"]);
          const next: Node = { ...cur };
          const data: Record<string, unknown> = { ...(cur.data ?? {}) };
          for (const [k, v] of Object.entries(fields)) {
            if (k === "data" && v && typeof v === "object") {
              Object.assign(next, { data: { ...(v as Record<string, unknown>) } });
            } else if (known.has(k)) {
              Object.assign(next, { [k]: v });
            } else {
              data[k] = v;
            }
          }
          if (!("data" in fields)) next.data = data;
          nodes[id] = next;
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
      case "EdgeUpdated": {
        // Mirror the backend reducer: top-level known fields are
        // overwritten directly; unknown keys merge into `data`. The
        // server sends the fields dict it received from the HTTP/MCP
        // patch — passing `data` as a whole dict replaces it, just like
        // the canonical reducer's `setattr(e, k, v)` path.
        const id = p.id as string;
        const fields = (p.fields as Record<string, unknown>) ?? {};
        if (edges[id]) {
          const cur = edges[id];
          const known = new Set(["label", "edge_type", "sourceHandle", "targetHandle", "data"]);
          const next: Edge = { ...cur };
          const data: Record<string, unknown> = { ...(cur.data ?? {}) };
          for (const [k, v] of Object.entries(fields)) {
            if (k === "data" && v && typeof v === "object") {
              // Replace whole data dict — matches `setattr(e, "data", v)`.
              Object.assign(next, { data: { ...(v as Record<string, unknown>) } });
            } else if (known.has(k)) {
              Object.assign(next, { [k]: v });
            } else {
              data[k] = v;
            }
          }
          // If nothing set `data` explicitly, the merged stray-keys map is what we keep.
          if (!("data" in fields)) next.data = data;
          edges[id] = next;
        }
        break;
      }
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
