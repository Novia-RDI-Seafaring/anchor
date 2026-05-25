/**
 * Pure align / distribute math — mirrors `core/workspace/align.py`.
 *
 * The two implementations are deliberately kept tiny and side-by-side so a
 * reader can verify the parity at a glance. The Python side is the source
 * of truth: the HTTP `align` / `distribute` endpoints recompute everything
 * server-side and stream the moves back over SSE. The TS version powers
 * the optimistic UI hint (e.g. a small disabled-state preview), and a few
 * unit tests; it is *not* the path that decides the final positions on the
 * canvas — that always goes through the backend.
 *
 * Why mirror it at all then: lint-imports keeps the architecture honest,
 * but the spec asks for a Vitest-tested `alignNodes` / `distributeNodes`
 * here. Having the function lets feature tests run without standing up
 * the FastAPI app.
 */
export type Anchor =
  | "top"
  | "bottom"
  | "left"
  | "right"
  | "center-h"
  | "center-v";

export type Distribute = "horizontal" | "vertical";

export type SelectedNode = {
  id: string;
  x: number;
  y: number;
  /** Optional. Falls back to 100 — same default the Python side uses. */
  width?: number;
  /** Optional. Falls back to 100 — same default the Python side uses. */
  height?: number;
};

const DEFAULT_DIM = 100;

function w(n: SelectedNode): number { return n.width ?? DEFAULT_DIM; }
function h(n: SelectedNode): number { return n.height ?? DEFAULT_DIM; }

/**
 * Align the input nodes' positions to a shared edge or midline.
 *
 * Returns a Map keyed by node id whose values are the new (x, y) ONLY for
 * nodes that genuinely move. Nodes already on the target line are omitted
 * so the caller (or the SSE consumer) doesn't fire no-op events.
 */
export function alignNodes(
  nodes: SelectedNode[],
  anchor: Anchor,
): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>();
  if (nodes.length < 2) return out;

  switch (anchor) {
    case "top": {
      const ty = Math.min(...nodes.map((n) => n.y));
      for (const n of nodes) if (n.y !== ty) out.set(n.id, { x: n.x, y: ty });
      return out;
    }
    case "bottom": {
      const tb = Math.max(...nodes.map((n) => n.y + h(n)));
      for (const n of nodes) {
        const ny = tb - h(n);
        if (n.y !== ny) out.set(n.id, { x: n.x, y: ny });
      }
      return out;
    }
    case "left": {
      const tx = Math.min(...nodes.map((n) => n.x));
      for (const n of nodes) if (n.x !== tx) out.set(n.id, { x: tx, y: n.y });
      return out;
    }
    case "right": {
      const tr = Math.max(...nodes.map((n) => n.x + w(n)));
      for (const n of nodes) {
        const nx = tr - w(n);
        if (n.x !== nx) out.set(n.id, { x: nx, y: n.y });
      }
      return out;
    }
    case "center-h": {
      // Share y centre — line lies halfway between topmost top and
      // bottommost bottom.
      const top = Math.min(...nodes.map((n) => n.y));
      const bot = Math.max(...nodes.map((n) => n.y + h(n)));
      const midY = (top + bot) / 2;
      for (const n of nodes) {
        const ny = midY - h(n) / 2;
        if (n.y !== ny) out.set(n.id, { x: n.x, y: ny });
      }
      return out;
    }
    case "center-v": {
      const left = Math.min(...nodes.map((n) => n.x));
      const right = Math.max(...nodes.map((n) => n.x + w(n)));
      const midX = (left + right) / 2;
      for (const n of nodes) {
        const nx = midX - w(n) / 2;
        if (n.x !== nx) out.set(n.id, { x: nx, y: n.y });
      }
      return out;
    }
  }
}

/**
 * Distribute the input nodes' centres evenly along ``axis``.
 *
 * End nodes stay put; the middle nodes get slotted so their centres lie on
 * equally-spaced points along the line between the endpoints. Needs at
 * least three nodes — for fewer, returns an empty map.
 */
export function distributeNodes(
  nodes: SelectedNode[],
  axis: Distribute,
): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>();
  if (nodes.length < 3) return out;

  if (axis === "horizontal") {
    const sorted = [...nodes].sort((a, b) => (a.x + w(a) / 2) - (b.x + w(b) / 2));
    const first = sorted[0]!;
    const last = sorted[sorted.length - 1]!;
    const firstC = first.x + w(first) / 2;
    const lastC = last.x + w(last) / 2;
    const step = (lastC - firstC) / (sorted.length - 1);
    sorted.forEach((n, i) => {
      const targetC = firstC + i * step;
      const newX = targetC - w(n) / 2;
      if (newX !== n.x) out.set(n.id, { x: newX, y: n.y });
    });
    return out;
  }

  // vertical
  const sorted = [...nodes].sort((a, b) => (a.y + h(a) / 2) - (b.y + h(b) / 2));
  const first = sorted[0]!;
  const last = sorted[sorted.length - 1]!;
  const firstC = first.y + h(first) / 2;
  const lastC = last.y + h(last) / 2;
  const step = (lastC - firstC) / (sorted.length - 1);
  sorted.forEach((n, i) => {
    const targetC = firstC + i * step;
    const newY = targetC - h(n) / 2;
    if (newY !== n.y) out.set(n.id, { x: n.x, y: newY });
  });
  return out;
}
