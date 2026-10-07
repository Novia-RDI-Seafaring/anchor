/**
 * preview.ts — what the canvas would look like if a suggestion were approved.
 *
 * A suggestion is a batch of canvas ops. The prose beside it says what the
 * agent means to do; the ops say exactly what will happen. Showing the reader
 * the prose and asking them to approve is asking them to trust a summary of
 * a change they could be looking at. So the ops are run forward here, against
 * the elements as they stand, and the result is drawn where it will land --
 * the new card with its rows, the changed card as it will read, the removed
 * card struck through, the new edges between them -- with approve beside it.
 *
 * Nothing here writes. It is the same reducer step the server will take on
 * approval, done ahead of time and thrown away.
 */

export type PreviewRow = { key: string; value: string };

export type PreviewNode = {
  id: string;
  kind: "added" | "updated" | "removed";
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  rows: PreviewRow[];
  /** For an update: what the card said before, so the reader can compare. */
  before?: { label: string; rows: PreviewRow[] };
};

export type PreviewEdge = {
  id: string;
  kind: "added" | "removed";
  source: string;
  target: string;
};

export type Preview = { nodes: PreviewNode[]; edges: PreviewEdge[] };

/** As much of a canvas node as a preview needs. */
export type NodeLike = {
  id: string;
  x: number;
  y: number;
  width?: number | null;
  height?: number | null;
  label?: string;
  data?: Record<string, unknown>;
};

export type EdgeLike = { id: string; source: string; target: string };

/** A card that gave no size: roughly what a spec card measures. */
const DEFAULT_W = 280;
const DEFAULT_H = 120;

function rowsOf(data: Record<string, unknown> | undefined): PreviewRow[] {
  const rows = data?.rows;
  if (!Array.isArray(rows)) return [];
  return rows.map((r) => ({
    key: String((r as { key?: unknown })?.key ?? ""),
    value: String((r as { value?: unknown })?.value ?? ""),
  }));
}

function labelOf(node: { label?: string; data?: Record<string, unknown> }): string {
  return String(node.data?.label ?? node.label ?? "");
}

/**
 * Run a suggestion's ops forward and report what changes, where.
 *
 * Ops later in the batch may refer to nodes added earlier in it, so the
 * batch is applied in order against a working copy. An op on a node that
 * does not exist is skipped rather than invented: the server would refuse
 * the whole batch, and a preview that showed something the server will not
 * do would be worse than none.
 */
export function previewOps(
  ops: Record<string, unknown>[],
  nodes: Record<string, NodeLike>,
  edges: EdgeLike[] = [],
): Preview {
  const working: Record<string, NodeLike> = { ...nodes };
  const out: Record<string, PreviewNode> = {};
  const outEdges: PreviewEdge[] = [];

  for (const op of ops) {
    const type = String(op.type ?? "");
    const payload = (op.payload ?? {}) as Record<string, unknown>;
    const id = String(payload.id ?? "");
    if (!id) continue;

    if (type === "NodeAdded") {
      const node: NodeLike = {
        id,
        x: Number(payload.x ?? 0),
        y: Number(payload.y ?? 0),
        width: payload.width == null ? null : Number(payload.width),
        height: payload.height == null ? null : Number(payload.height),
        label: payload.label == null ? undefined : String(payload.label),
        data: (payload.data as Record<string, unknown> | undefined) ?? {},
      };
      working[id] = node;
      out[id] = {
        id,
        kind: "added",
        x: node.x,
        y: node.y,
        width: node.width ?? DEFAULT_W,
        height: node.height ?? DEFAULT_H,
        label: labelOf(node),
        rows: rowsOf(node.data),
      };
      continue;
    }

    if (type === "NodeUpdated") {
      const was = working[id];
      if (!was) continue;
      const fields = (payload.fields ?? {}) as Record<string, unknown>;
      const next: NodeLike = {
        ...was,
        ...(fields.x != null ? { x: Number(fields.x) } : {}),
        ...(fields.y != null ? { y: Number(fields.y) } : {}),
        ...(fields.label != null ? { label: String(fields.label) } : {}),
        ...(fields.data != null ? { data: fields.data as Record<string, unknown> } : {}),
      };
      working[id] = next;
      // A node added and then updated in the same batch is still "added".
      const prior = out[id];
      out[id] = {
        id,
        kind: prior?.kind === "added" ? "added" : "updated",
        x: next.x,
        y: next.y,
        width: next.width ?? DEFAULT_W,
        height: next.height ?? DEFAULT_H,
        label: labelOf(next),
        rows: rowsOf(next.data),
        ...(prior?.kind === "added"
          ? {}
          : { before: prior?.before ?? { label: labelOf(was), rows: rowsOf(was.data) } }),
      };
      continue;
    }

    if (type === "NodeRemoved") {
      const was = working[id];
      if (!was) continue;
      delete working[id];
      out[id] = {
        id,
        kind: "removed",
        x: was.x,
        y: was.y,
        width: was.width ?? DEFAULT_W,
        height: was.height ?? DEFAULT_H,
        label: labelOf(was),
        rows: rowsOf(was.data),
      };
      continue;
    }

    if (type === "EdgeAdded") {
      const source = String(payload.source ?? "");
      const target = String(payload.target ?? "");
      if (!working[source] || !working[target]) continue;
      outEdges.push({ id, kind: "added", source, target });
      continue;
    }

    if (type === "EdgeRemoved") {
      const was = edges.find((e) => e.id === id);
      if (!was) continue;
      outEdges.push({ id, kind: "removed", source: was.source, target: was.target });
    }
  }

  return { nodes: Object.values(out), edges: outEdges };
}

/** Where an element's centre will be after the batch: previewed, or as it is. */
export function previewCentre(
  id: string,
  preview: Preview,
  nodes: Record<string, NodeLike>,
): { x: number; y: number } | null {
  const p = preview.nodes.find((n) => n.id === id);
  if (p) return { x: p.x + p.width / 2, y: p.y + p.height / 2 };
  const n = nodes[id];
  if (!n) return null;
  return { x: n.x + (n.width ?? DEFAULT_W) / 2, y: n.y + (n.height ?? DEFAULT_H) / 2 };
}
