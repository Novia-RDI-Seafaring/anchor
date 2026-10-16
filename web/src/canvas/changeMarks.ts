/**
 * changeMarks.ts — which real elements an applied change touched.
 *
 * An agent that acts puts real cards on the canvas and asks the reader to
 * keep them or put them back. Until the reader rules, the cards should say
 * so: they are real, but not yet accepted. The ghost style already means
 * "not real yet", so these marks are solid instead -- a ring in the remark's
 * colour and a small tag -- on the elements themselves.
 *
 * Nothing new is needed from the server to know which elements those are.
 * The undo ops recorded at apply time name them: undoing an add removes the
 * id the add was given, undoing an update restores the old fields, undoing a
 * removal re-adds the element as it was.
 */
import type { ChangeMark, ShownMark } from "@/intent-overlay";
import { previewCentre, previewOps, type EdgeLike, type NodeLike, type Preview } from "./preview";

export type CanvasChanges = {
  marks: ChangeMark[];
  /** What the change took away, drawn where it stood. */
  removed: Preview;
};

function labelOf(node: NodeLike | undefined): string {
  return String(node?.data?.label ?? node?.label ?? "");
}

/** Read an applied suggestion's undo ops back into what it changed. */
export function changesOf(
  undo: Record<string, unknown>[] | undefined,
  nodes: Record<string, NodeLike>,
  edges: Record<string, EdgeLike>,
): CanvasChanges {
  const marks = new Map<string, ChangeMark>();
  const gone: Record<string, unknown>[] = [];
  for (const op of undo ?? []) {
    const payload = (op.payload ?? {}) as Record<string, unknown>;
    const id = String(payload.id ?? "");
    if (!id) continue;
    switch (op.type) {
      case "NodeRemoved":
        if (nodes[id]) marks.set(`node:${id}`, { id, element: "node", kind: "added" });
        break;
      case "NodeUpdated": {
        if (!nodes[id] || marks.has(`node:${id}`)) break;
        const fields = (payload.fields ?? {}) as Record<string, unknown>;
        const was = fields.label == null ? undefined : String(fields.label);
        marks.set(`node:${id}`, {
          id, element: "node", kind: "updated",
          ...(was !== undefined && was !== labelOf(nodes[id]) ? { was } : {}),
        });
        break;
      }
      case "EdgeRemoved":
        if (edges[id]) marks.set(`edge:${id}`, { id, element: "edge", kind: "added" });
        break;
      case "EdgeUpdated":
        if (edges[id] && !marks.has(`edge:${id}`)) marks.set(`edge:${id}`, { id, element: "edge", kind: "updated" });
        break;
      // Re-adding something still there would be no removal at all.
      case "NodeAdded":
        if (!nodes[id]) gone.push(op);
        break;
      case "EdgeAdded":
        if (!edges[id]) gone.push(op);
        break;
    }
  }
  const back = previewOps(gone, nodes, Object.values(edges));
  return {
    marks: [...marks.values()],
    removed: {
      nodes: back.nodes.map((n) => ({ ...n, kind: "removed" })),
      edges: back.edges.map((e) => ({ ...e, kind: "removed" })),
    },
  };
}

/** Endpoints for the removed edges, as the overlay draws them. */
export function removedEdgeEnds(removed: Preview, nodes: Record<string, NodeLike>) {
  return removed.edges.map((edge) => ({
    id: edge.id, kind: edge.kind,
    from: previewCentre(edge.source, removed, nodes),
    to: previewCentre(edge.target, removed, nodes),
  }));
}

const STYLE_ID = "anchor-change-marks";

function attr(id: string): string {
  return typeof CSS !== "undefined" && CSS.escape ? CSS.escape(id) : id.replace(/["\\]/g, "\\$&");
}

function text(value: string): string {
  return JSON.stringify(value.replace(/\s+/g, " "));
}

function rules(mark: ShownMark): string {
  const c = mark.color;
  const halo = mark.strong ? `box-shadow: 0 0 0 7px color-mix(in srgb, ${c} 22%, transparent);` : "";
  if (mark.element === "edge") {
    return `.react-flow__edge[data-id="${attr(mark.id)}"] path:not(.react-flow__edge-interaction) {
  stroke: ${c} !important; stroke-width: ${mark.strong ? 4 : 3}px !important;
}`;
  }
  const node = `.react-flow__node[data-id="${attr(mark.id)}"]`;
  const tag = mark.kind === "added" ? "new" : "changed";
  const out = [`${node} {
  outline: ${mark.strong ? 3 : 2}px solid ${c}; outline-offset: 4px; border-radius: 10px; ${halo}
}`, `${node}::after {
  content: ${text(tag)}; position: absolute; top: -11px; right: -8px; z-index: 10;
  padding: 2px 7px; border-radius: 999px; background: ${c}; color: white;
  font: 600 10px/1.4 system-ui, sans-serif; letter-spacing: 0.03em; pointer-events: none;
}`];
  if (mark.was !== undefined) {
    out.push(`${node}::before {
  content: ${text(mark.was)}; position: absolute; top: 100%; left: 0; margin-top: 7px;
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: rgb(115,115,115); text-decoration: line-through; font: 11px/1.3 system-ui, sans-serif;
  pointer-events: none;
}`);
  }
  return out.join("\n");
}

/** Draw the marks on the real elements; an empty list takes them all off. */
export function markChanges(marks: ShownMark[]): void {
  let el = document.getElementById(STYLE_ID);
  if (marks.length === 0) {
    el?.remove();
    return;
  }
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = marks.map(rules).join("\n");
}
