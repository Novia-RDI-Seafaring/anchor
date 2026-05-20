/**
 * JsonEscapeHatch — last-resort raw `data` editor.
 *
 * Used by the Properties panel for node types that don't (yet) have a
 * bespoke editor: `model3d`, `cad:model`, `sysml:block`, future plugins,
 * etc. Surfaces the raw `data` dict as JSON in a textarea so power-users
 * can still tweak fields. Always also exposes `label` as a plain input.
 *
 * Validation: parses the textarea on every change. Invalid JSON shows an
 * inline error; nothing is sent to the server until the parse succeeds.
 * This is a deliberate "advanced" panel — users without a JSON intuition
 * shouldn't be here. Power-users can ship one-off fixes.
 */
import { useEffect, useState } from "react";

import { LabelEditor } from "./LabelEditor";
import { usePatchNode } from "./_usePatchNode";
import type { EditorProps } from "./_types";

function stringify(data: Record<string, unknown> | undefined): string {
  try {
    return JSON.stringify(data ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

export function JsonEscapeHatch({ workspaceSlug, node }: EditorProps) {
  const { patch, error: saveError } = usePatchNode(workspaceSlug, node.id);
  const [draft, setDraft] = useState(stringify(node.data));
  const [parseError, setParseError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(stringify(node.data));
    setParseError(null);
  }, [node.data, node.id]);

  return (
    <div className="flex flex-col gap-3">
      <LabelEditor workspaceSlug={workspaceSlug} node={node} />

      <details className="rounded border border-neutral-200">
        <summary className="cursor-pointer select-none px-2 py-1.5 text-[11px] font-medium uppercase tracking-wide text-neutral-500 hover:bg-neutral-50">
          Advanced — raw data JSON
        </summary>
        <div className="border-t border-neutral-200 p-2">
          <div className="mb-1 text-[11px] text-neutral-500">
            No custom editor for <code className="rounded bg-neutral-100 px-1">{node.node_type}</code> yet.
            Edit the underlying <code className="rounded bg-neutral-100 px-1">data</code> JSON directly. Invalid JSON is not saved.
          </div>
          <textarea
            value={draft}
            onChange={(e) => {
              const next = e.target.value;
              setDraft(next);
              try {
                const parsed = JSON.parse(next);
                if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
                  setParseError("Top level must be a JSON object.");
                  return;
                }
                setParseError(null);
                patch({ data: parsed });
              } catch (err) {
                setParseError(err instanceof Error ? err.message : "invalid JSON");
              }
            }}
            rows={14}
            spellCheck={false}
            className="w-full resize-y rounded border border-neutral-300 bg-neutral-50 px-2 py-1.5 font-mono text-[11px] leading-snug outline-none focus:border-neutral-500"
          />
          {parseError ? (
            <div className="mt-1 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] text-amber-800">
              {parseError}
            </div>
          ) : null}
          {saveError ? (
            <div className="mt-1 rounded border border-red-300 bg-red-50 px-2 py-1 text-[11px] text-red-700">
              Save failed: {saveError}
            </div>
          ) : null}
        </div>
      </details>
    </div>
  );
}
