/**
 * MarkdownEditor — label + body editor for Fact and Note nodes.
 *
 * Renderers (`FactNode`, `NoteNode`) read body content from `data.text`
 * today, so we PATCH `data: { ...existing, text: next }`. The task spec
 * mentions `data.body` — we follow the actual renderer field. When/if
 * the renderers migrate to `data.body`, swap the key in one place here.
 *
 * No markdown preview pane in this iteration — fact/note bodies are
 * short. Add one when bodies grow long enough to warrant it.
 */
import { useEffect, useState } from "react";

import { LabelEditor } from "./LabelEditor";
import { usePatchNode } from "./_usePatchNode";
import type { EditorProps } from "./_types";

export function MarkdownEditor({ workspaceSlug, node }: EditorProps) {
  const { patch, error } = usePatchNode(workspaceSlug, node.id);
  const initial = (node.data?.text as string | undefined) ?? "";
  const [value, setValue] = useState(initial);

  useEffect(() => {
    setValue((node.data?.text as string | undefined) ?? "");
  }, [node.data, node.id]);

  return (
    <div className="flex flex-col gap-3">
      <LabelEditor workspaceSlug={workspaceSlug} node={node} />
      <div className="flex flex-col gap-1">
        <label htmlFor="md-body-input" className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
          Body
        </label>
        <textarea
          id="md-body-input"
          value={value}
          onChange={(e) => {
            const next = e.target.value;
            setValue(next);
            // Merge with existing data so we don't trample sibling fields
            // (pictogram, dashed, etc.). The server replaces `data` whole,
            // so client-side merge is mandatory.
            patch({ data: { ...(node.data ?? {}), text: next } });
          }}
          placeholder="Type the body of the note. Plain text and line breaks; markdown rendering is a follow-up."
          rows={10}
          className="resize-y rounded border border-neutral-300 bg-white px-2 py-1.5 font-mono text-[12px] leading-snug outline-none focus:border-neutral-500"
        />
        {error ? (
          <div className="rounded border border-red-300 bg-red-50 px-2 py-1 text-[11px] text-red-700">
            Save failed: {error}
          </div>
        ) : null}
      </div>
    </div>
  );
}
