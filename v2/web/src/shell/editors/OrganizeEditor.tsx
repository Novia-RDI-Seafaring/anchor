/**
 * OrganizeEditor — buttons that re-lay-out the selected node's subtree.
 *
 * Renders inside `PropertiesPanel` underneath whatever editor matches the
 * node's `node_type`. Available whenever the selected node has at least
 * one connected edge — we treat connected nodes as a tree rooted at the
 * selection, the same way the server-side organizer does (undirected BFS
 * over the edge set; root stays put; descendants get tidy positions).
 *
 * The three orientations match the spec:
 *   - Vertical / Horizontal: hit `POST /api/workspaces/<slug>/layout`,
 *     which streams back a flurry of `NodeMoved` events via SSE. The
 *     canvas store's version-monotonic `applyEvent` accumulates them and
 *     ReactFlow re-renders the new positions with its built-in transition.
 *   - Radial: stubbed. d3-hierarchy isn't a dep today; if/when we add
 *     polar projection the same button calls the same endpoint with
 *     `algo='radial'`. Disabled with a tooltip-on-title so users see why.
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

export function OrganizeEditor({ workspaceSlug, nodeId, hasChildren }: Props) {
  const [busy, setBusy] = useState<Orientation | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!hasChildren) return null;

  const run = async (orientation: Orientation) => {
    setBusy(orientation);
    setError(null);
    try {
      // The SSE feed echoes each NodeMoved back into the canvas store;
      // no need to wire the response.moves array through ourselves.
      await canvases.organizeSubtree(workspaceSlug, nodeId, orientation);
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
