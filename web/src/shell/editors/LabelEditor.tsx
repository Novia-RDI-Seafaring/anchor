/**
 * LabelEditor — single-line text input bound to `node.label`.
 *
 * Used by the Properties panel for shape primitives (concept, entity,
 * funnel, area). The canvas also exposes an inline rename via
 * `useInlineLabel` — this panel-side editor is a stable alternative for
 * users who prefer a side rail over double-clicking the shape.
 *
 * Edits debounce 300ms (see `_usePatchNode`); the SSE echo reconciles
 * back into the store and re-feeds this component via `node.label`.
 */
import { useEffect, useState } from "react";

import { usePatchNode } from "./_usePatchNode";
import type { EditorProps } from "./_types";

export function LabelEditor({ workspaceSlug, node }: EditorProps) {
  const { patch, error } = usePatchNode(workspaceSlug, node.id);
  const [value, setValue] = useState(node.label ?? "");

  // Reflect external label changes (SSE echo, remote edit) when we're not
  // actively diverging from the canonical value.
  useEffect(() => { setValue(node.label ?? ""); }, [node.label, node.id]);

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="label-input" className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
        Label
      </label>
      <input
        id="label-input"
        type="text"
        value={value}
        onChange={(e) => {
          const next = e.target.value;
          setValue(next);
          patch({ label: next });
        }}
        placeholder="untitled"
        className="rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm outline-none focus:border-neutral-500"
      />
      {error ? (
        <div className="rounded border border-red-300 bg-red-50 px-2 py-1 text-[11px] text-red-700">
          Save failed: {error}
        </div>
      ) : null}
    </div>
  );
}
