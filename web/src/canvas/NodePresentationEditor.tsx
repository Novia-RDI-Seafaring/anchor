import { useState } from "react";

import { canvases } from "@/api/canvases";
import { COMPACT_CARD_TYPES, collapseDirection, type StructureNode } from "@/canvas/subtrees";

export function NodePresentationEditor({ workspaceSlug, node }: { workspaceSlug: string; node: StructureNode }) {
  const [error, setError] = useState<string | null>(null);
  const update = async (data: Record<string, unknown>) => {
    try {
      await canvases.patchNode(workspaceSlug, node.id, { data });
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };
  return (
    <section className="mb-2 flex flex-col gap-2 text-xs" aria-label="Node presentation">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">Presentation</div>
      {node.node_type === "concept" ? <label className="flex items-center justify-between gap-2">
        Appearance
        <select aria-label="Node appearance" className="rounded border bg-white px-1 py-1"
          value={node.data?.role === "heading" ? "heading" : "card"}
          onChange={(event) => void update({ role: event.target.value === "heading" ? "heading" : null })}>
          <option value="card">Card</option><option value="heading">Heading</option>
        </select>
      </label> : null}
      {COMPACT_CARD_TYPES.has(node.node_type) ? <label className="flex items-center justify-between gap-2">
        Display
        <select aria-label="Node display" className="rounded border bg-white px-1 py-1"
          value={node.data?.display_mode === "full" ? "full" : "compact"}
          onChange={(event) => void update({ display_mode: event.target.value })}>
          <option value="compact">Compact</option><option value="full">Full</option>
        </select>
      </label> : null}
      <label className="flex items-center justify-between gap-2">
        Child direction
        <select aria-label="Subtree direction" className="rounded border bg-white px-1 py-1"
          value={collapseDirection(node)} onChange={(event) => void update({ collapse_direction: event.target.value })}>
          <option value="outgoing">Outgoing</option><option value="incoming">Incoming</option><option value="any">Any</option>
        </select>
      </label>
      {error ? <p role="alert" className="text-red-700">Save failed: {error}</p> : null}
    </section>
  );
}
