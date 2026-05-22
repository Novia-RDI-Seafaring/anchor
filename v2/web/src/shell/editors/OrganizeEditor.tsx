/**
 * OrganizeEditor — buttons that re-lay-out the selected node's subtree.
 *
 * Renders inside `PropertiesPanel` underneath whatever editor matches the
 * node's `node_type`. Available whenever the selected node has at least
 * one connected edge — we treat connected nodes as a tree rooted at the
 * selection, the same way the server-side organizer does.
 *
 * Two knobs:
 *   - **Orientation**: vertical / horizontal / radial(stub). Vertical and
 *     horizontal hit `POST /api/workspaces/<slug>/layout`, which streams
 *     back a flurry of `NodeMoved` events via SSE.
 *   - **Direction** (new — 2026-05): controls the BFS edge-walk. The bug
 *     this fixes is that an undirected walk from a mid-tree node (CFO on
 *     the `acme-org` canvas) drags the parent (CEO) in too because the
 *     edge connects them either way. Three modes:
 *       ↓ `outgoing` — follow arrows forward (parent → child).
 *       ↑ `incoming` — follow arrows backward (reports-to convention).
 *       ↔ `any`     — undirected, the v1 default. Use this when the
 *                     canvas convention is mixed.
 *
 *     The default stays `any` so existing UX doesn't shift under users.
 *     Per-component state, not persisted server-side — the user can re-pick
 *     per organise gesture.
 *
 * Why a separate "Layout" section instead of a new dispatched editor:
 * organize is orthogonal to node_type — it makes equal sense for entities,
 * concepts, document cards, anything. Folding it into the existing
 * dispatch would either duplicate the buttons across every editor or
 * force a single "tree node" editor that swallows everything else.
 */
import { useState } from "react";

import { canvases } from "@/api/canvases";
import { Button } from "@/components/ui/button";

type Props = {
  workspaceSlug: string;
  nodeId: string;
  /** Whether the node has at least one connected edge. Section is hidden
   * entirely when false — there's no subtree to organize. */
  hasChildren: boolean;
};

type Orientation = "vertical" | "horizontal";
type Direction = "outgoing" | "incoming" | "any";

const DIRECTION_OPTIONS: ReadonlyArray<{
  value: Direction;
  glyph: string;
  label: string;
  title: string;
}> = [
  {
    value: "outgoing",
    glyph: "↓",
    label: "Outgoing",
    title:
      "Outgoing — follow arrows forward (parent → child). Use when the canvas convention is cause → effect or container → contained.",
  },
  {
    value: "incoming",
    glyph: "↑",
    label: "Incoming",
    title:
      "Incoming — follow arrows backward (subordinate → boss). Use on a reports-to org chart so the BFS doesn't drag the parent in.",
  },
  {
    value: "any",
    glyph: "↔",
    label: "Any",
    title:
      "Any direction — undirected walk. The original behaviour; use it when the canvas convention is mixed and you want every connected node.",
  },
];

export function OrganizeEditor({ workspaceSlug, nodeId, hasChildren }: Props) {
  const [busy, setBusy] = useState<Orientation | null>(null);
  const [direction, setDirection] = useState<Direction>("any");
  const [error, setError] = useState<string | null>(null);

  if (!hasChildren) return null;

  const run = async (orientation: Orientation) => {
    setBusy(orientation);
    setError(null);
    try {
      // The SSE feed echoes each NodeMoved back into the canvas store;
      // no need to wire the response.moves array through ourselves.
      await canvases.organizeSubtree(
        workspaceSlug,
        nodeId,
        orientation,
        "dagre",
        direction,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="mt-4 border-t border-neutral-200 pt-3">
      <h3 className="mb-1 text-[11px] font-medium uppercase tracking-wide text-neutral-500">
        Layout
      </h3>
      <p className="mb-2 text-[11px] text-neutral-500">
        Re-arrange the subtree under this node. The selected node stays put.
      </p>
      <div className="mb-2">
        <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-400">
          Direction
        </div>
        <div
          role="radiogroup"
          aria-label="Edge-walk direction"
          className="flex gap-1"
        >
          {DIRECTION_OPTIONS.map((opt) => {
            const selected = opt.value === direction;
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={selected}
                aria-label={`${opt.label} — ${opt.title}`}
                title={opt.title}
                onClick={() => setDirection(opt.value)}
                disabled={busy !== null}
                className={
                  "inline-flex h-7 min-w-[2rem] items-center justify-center rounded border px-2 text-[12px] " +
                  (selected
                    ? "border-neutral-800 bg-neutral-900 text-white"
                    : "border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-100")
                }
              >
                {opt.glyph}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Button
          variant="outline"
          size="sm"
          disabled={busy !== null}
          onClick={() => void run("vertical")}
          aria-label="Organize subtree vertically"
        >
          {busy === "vertical" ? "Organizing…" : "Vertical"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={busy !== null}
          onClick={() => void run("horizontal")}
          aria-label="Organize subtree horizontally"
        >
          {busy === "horizontal" ? "Organizing…" : "Horizontal"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled
          aria-label="Radial layout (coming soon)"
          title="Radial layout — coming soon"
        >
          Radial
        </Button>
      </div>
      {error ? (
        <div className="mt-2 rounded border border-red-300 bg-red-50 px-2 py-1 text-[11px] text-red-700">
          Organize failed: {error}
        </div>
      ) : null}
    </section>
  );
}
