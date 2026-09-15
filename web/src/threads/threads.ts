/**
 * threads.ts — pure helpers for scoped-ask threads (#344).
 *
 * A thread is an intent with `targets[]` (the lassoed selection) and typed
 * `items` (message / question / suggestion / result). Everything here is
 * side-effect free and canvas-store agnostic: callers pass the node / edge
 * maps in, and get plain data out. The overlays (pins, composer, ghost
 * preview) and the panel render from these results; none of them may
 * write to the workspace store, and this module makes that easy to keep.
 */
import type { Intent, ThreadItem, ThreadOp } from "@/api/intents";

/** The minimal node shape the helpers need (a subset of canvasStore's Node). */
export type ThreadNode = {
  id: string;
  node_type: string;
  label: string;
  x: number;
  y: number;
  width?: number | null;
  height?: number | null;
  data?: Record<string, unknown>;
};

export type ThreadEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;
};

export type Rect = { x: number; y: number; width: number; height: number };

/** Fallback footprint for nodes that carry no size (matches the toolbar). */
export const DEFAULT_NODE_SIZE = 100;

/** Rendered footprint of a node in flow space. Top-level `width`/`height`
 *  win; legacy `data.width`/`data.height` next; then the shared default. */
export function nodeRect(n: ThreadNode): Rect {
  const d = (n.data ?? {}) as { width?: unknown; height?: unknown };
  const width =
    (typeof n.width === "number" ? n.width : null) ??
    (typeof d.width === "number" ? d.width : null) ??
    DEFAULT_NODE_SIZE;
  const height =
    (typeof n.height === "number" ? n.height : null) ??
    (typeof d.height === "number" ? d.height : null) ??
    DEFAULT_NODE_SIZE;
  return { x: n.x, y: n.y, width, height };
}

/** Bounding box (flow space) of the listed nodes that exist. Null when none do. */
export function boundingBox(
  nodeIds: readonly string[],
  nodes: Record<string, ThreadNode>,
): Rect | null {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const id of nodeIds) {
    const n = nodes[id];
    if (!n) continue;
    const r = nodeRect(n);
    if (r.x < minX) minX = r.x;
    if (r.y < minY) minY = r.y;
    if (r.x + r.width > maxX) maxX = r.x + r.width;
    if (r.y + r.height > maxY) maxY = r.y + r.height;
  }
  if (!Number.isFinite(minX)) return null;
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

// ---------------------------------------------------------------------------
// Composer chips
// ---------------------------------------------------------------------------

/**
 * Suggested asks for a selection, derived from the selected node types.
 * Exact texts per the issue: spec → fill / verify; document → extract;
 * chart → digitize; two or more nodes → compare / consistency; and the
 * defaults always close the list. Order is stable; duplicates collapse.
 */
export function chipsForSelection(nodeTypes: readonly string[]): string[] {
  const types = new Set(nodeTypes);
  const chips: string[] = [];
  if (types.has("spec")) {
    chips.push("Fill the missing values from the documents", "Verify these against the source");
  }
  if (types.has("document")) chips.push("Extract the specs into a table");
  if (types.has("chart")) chips.push("Digitize this curve");
  if (nodeTypes.length >= 2) chips.push("Compare these", "Check consistency");
  chips.push("Make sense of this", "Name and group these");
  return Array.from(new Set(chips));
}

// ---------------------------------------------------------------------------
// Threads on a canvas, pins
// ---------------------------------------------------------------------------

/** Target node ids of `intent` that live on `workspaceSlug`. */
export function targetsOnCanvas(intent: Intent, workspaceSlug: string): string[] {
  return (intent.targets ?? [])
    .filter((t) => t.workspace_id === workspaceSlug && typeof t.node_id === "string")
    .map((t) => t.node_id);
}

/** True when the intent is an open thread anchored to something on this canvas. */
export function isOpenThreadOn(intent: Intent, workspaceSlug: string): boolean {
  return intent.status === "pending" && targetsOnCanvas(intent, workspaceSlug).length > 0;
}

export type ThreadPin = {
  /** Stable key for the marker: its anchor point (rounded flow coords). */
  key: string;
  /** Top-right corner of the targets' bounding box, flow space. */
  x: number;
  y: number;
  /** Threads anchored here, oldest first. Several → count badge. */
  threadIds: string[];
  /** Node ids the pin covers (union across its threads). */
  nodeIds: string[];
};

/**
 * One marker per distinct anchor point. A thread whose targets no longer
 * exist on the canvas has nothing to anchor to and yields no pin; threads
 * sharing an anchor collapse into one marker with a count.
 */
export function pinsForCanvas(
  intents: readonly Intent[],
  workspaceSlug: string,
  nodes: Record<string, ThreadNode>,
): ThreadPin[] {
  const byKey = new Map<string, ThreadPin>();
  const sorted = [...intents].sort(
    (a, b) => a.created_at - b.created_at || a.id.localeCompare(b.id),
  );
  for (const intent of sorted) {
    if (!isOpenThreadOn(intent, workspaceSlug)) continue;
    const ids = targetsOnCanvas(intent, workspaceSlug).filter((id) => nodes[id]);
    const box = boundingBox(ids, nodes);
    if (!box) continue;
    const x = box.x + box.width;
    const y = box.y;
    const key = `${Math.round(x)}:${Math.round(y)}`;
    const pin = byKey.get(key);
    if (pin) {
      pin.threadIds.push(intent.id);
      for (const id of ids) if (!pin.nodeIds.includes(id)) pin.nodeIds.push(id);
    } else {
      byKey.set(key, { key, x, y, threadIds: [intent.id], nodeIds: [...ids] });
    }
  }
  return Array.from(byKey.values());
}

// ---------------------------------------------------------------------------
// Items
// ---------------------------------------------------------------------------

/** Items in thread order: created_at, then id for ties. */
export function orderedItems(intent: Intent | null | undefined): ThreadItem[] {
  return [...(intent?.items ?? [])].sort(
    (a, b) => a.created_at - b.created_at || a.id.localeCompare(b.id),
  );
}

export function findItem(intent: Intent | null | undefined, itemId: string | null): ThreadItem | null {
  if (!itemId) return null;
  return intent?.items?.find((i) => i.id === itemId) ?? null;
}

export function isSuggestion(item: ThreadItem): boolean {
  return item.type === "suggestion";
}

export function opCount(item: ThreadItem): number {
  return Array.isArray(item.ops) ? item.ops.length : 0;
}

/** The ask text (the thread's title). */
export function threadTitle(intent: Intent): string {
  const text = typeof intent.payload.text === "string" ? intent.payload.text.trim() : "";
  return text || "Ask";
}

/** Display name for an item author. */
export function authorName(author: ThreadItem["author"] | null | undefined): string {
  if (!author) return "";
  return author.label || author.kind;
}

// ---------------------------------------------------------------------------
// Staleness and ghost preview
// ---------------------------------------------------------------------------

/**
 * Ids a batch's ops reference that must already exist on the canvas, in
 * batch order: update/remove targets, and edge endpoints that are not
 * client ids minted by an earlier `NodeAdded` in the same batch.
 */
export function referencedExistingIds(ops: readonly ThreadOp[]): {
  nodeIds: string[];
  edgeIds: string[];
} {
  const minted = new Set<string>();
  const nodeIds: string[] = [];
  const edgeIds: string[] = [];
  for (const op of ops) {
    switch (op.type) {
      case "NodeAdded":
        if (op.payload.id) minted.add(op.payload.id);
        break;
      case "NodeUpdated":
      case "NodeRemoved":
        nodeIds.push(op.payload.id);
        break;
      case "EdgeAdded":
        if (op.payload.id) minted.add(op.payload.id);
        if (!minted.has(op.payload.source)) nodeIds.push(op.payload.source);
        if (!minted.has(op.payload.target)) nodeIds.push(op.payload.target);
        break;
      case "EdgeUpdated":
      case "EdgeRemoved":
        if (!minted.has(op.payload.id)) edgeIds.push(op.payload.id);
        break;
    }
  }
  return { nodeIds, edgeIds };
}

/**
 * A pending suggestion is stale when any op references an element that no
 * longer exists. Applied / declined / superseded suggestions are history and
 * never stale.
 */
export function isStaleSuggestion(
  item: ThreadItem,
  nodes: Record<string, ThreadNode>,
  edges: Record<string, ThreadEdge>,
): boolean {
  if (item.type !== "suggestion" || item.state !== "pending") return false;
  const { nodeIds, edgeIds } = referencedExistingIds(item.ops ?? []);
  return nodeIds.some((id) => !nodes[id]) || edgeIds.some((id) => !edges[id]);
}

export type GhostNode = {
  kind: "node-added" | "node-removed" | "node-updated";
  id: string;
  rect: Rect;
  label: string;
  node_type: string;
  /** node-updated only: label before → after (after is `label`). */
  oldLabel?: string;
  /** node-updated only: which fields the op touches. */
  fields?: string[];
  /** The referenced element is gone (stale op). */
  missing?: boolean;
};

export type GhostEdge = {
  kind: "edge-added" | "edge-removed" | "edge-updated";
  id: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
  label?: string;
  missing?: boolean;
};

export type GhostElements = { nodes: GhostNode[]; edges: GhostEdge[] };

/** Where an added node lands by default when the op carries no size. */
const GHOST_ADDED_SIZE = { width: 160, height: 72 };

function center(r: Rect): { x: number; y: number } {
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
}

/**
 * Project a suggestion's ops onto overlay elements. Purely derived: the
 * canvas maps are read, never written. Client ids minted by `NodeAdded`
 * resolve later edge endpoints to the ghost's own rect.
 */
export function ghostElementsFromOps(
  ops: readonly ThreadOp[],
  nodes: Record<string, ThreadNode>,
  edges: Record<string, ThreadEdge>,
): GhostElements {
  const out: GhostElements = { nodes: [], edges: [] };
  // Rect lookup for edge endpoints: real nodes plus ghosts added so far.
  const rects = new Map<string, Rect>();
  const rectOf = (id: string): Rect | null => {
    const g = rects.get(id);
    if (g) return g;
    const n = nodes[id];
    return n ? nodeRect(n) : null;
  };
  let mint = 0;
  for (const op of ops) {
    switch (op.type) {
      case "NodeAdded": {
        const p = op.payload;
        const id = p.id ?? `ghost-${++mint}`;
        const rect: Rect = {
          x: p.x ?? 0,
          y: p.y ?? 0,
          width: typeof p.width === "number" ? p.width : GHOST_ADDED_SIZE.width,
          height: typeof p.height === "number" ? p.height : GHOST_ADDED_SIZE.height,
        };
        rects.set(id, rect);
        out.nodes.push({
          kind: "node-added",
          id,
          rect,
          label: p.label ?? "",
          node_type: p.node_type ?? "concept",
        });
        break;
      }
      case "NodeRemoved": {
        const n = nodes[op.payload.id];
        if (!n) {
          out.nodes.push({
            kind: "node-removed",
            id: op.payload.id,
            rect: { x: 0, y: 0, width: 0, height: 0 },
            label: op.payload.id,
            node_type: "",
            missing: true,
          });
          break;
        }
        out.nodes.push({
          kind: "node-removed",
          id: n.id,
          rect: nodeRect(n),
          label: n.label,
          node_type: n.node_type,
        });
        break;
      }
      case "NodeUpdated": {
        const n = nodes[op.payload.id];
        const fields = op.payload.fields ?? {};
        const newLabel = typeof fields.label === "string" ? fields.label : undefined;
        if (!n) {
          out.nodes.push({
            kind: "node-updated",
            id: op.payload.id,
            rect: { x: 0, y: 0, width: 0, height: 0 },
            label: newLabel ?? op.payload.id,
            node_type: "",
            fields: Object.keys(fields),
            missing: true,
          });
          break;
        }
        out.nodes.push({
          kind: "node-updated",
          id: n.id,
          rect: nodeRect(n),
          label: newLabel ?? n.label,
          oldLabel: newLabel !== undefined ? n.label : undefined,
          node_type: n.node_type,
          fields: Object.keys(fields),
        });
        break;
      }
      case "EdgeAdded": {
        const a = rectOf(op.payload.source);
        const b = rectOf(op.payload.target);
        const id = op.payload.id ?? `ghost-edge-${++mint}`;
        if (!a || !b) {
          out.edges.push({
            kind: "edge-added",
            id,
            from: { x: 0, y: 0 },
            to: { x: 0, y: 0 },
            label: op.payload.label,
            missing: true,
          });
          break;
        }
        out.edges.push({ kind: "edge-added", id, from: center(a), to: center(b), label: op.payload.label });
        break;
      }
      case "EdgeRemoved":
      case "EdgeUpdated": {
        const e = edges[op.payload.id];
        const kind = op.type === "EdgeRemoved" ? "edge-removed" : "edge-updated";
        const a = e ? rectOf(e.source) : null;
        const b = e ? rectOf(e.target) : null;
        if (!e || !a || !b) {
          out.edges.push({ kind, id: op.payload.id, from: { x: 0, y: 0 }, to: { x: 0, y: 0 }, missing: true });
          break;
        }
        const label =
          op.type === "EdgeUpdated" && typeof op.payload.fields?.label === "string"
            ? (op.payload.fields.label as string)
            : e.label;
        out.edges.push({ kind, id: e.id, from: center(a), to: center(b), label });
        break;
      }
    }
  }
  return out;
}
