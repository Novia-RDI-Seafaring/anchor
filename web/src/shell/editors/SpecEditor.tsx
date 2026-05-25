/**
 * SpecEditor — Properties panel editor for `spec` nodes.
 *
 * In-scope today:
 *   - Label (the spec table's heading)
 *   - Description (free-form text, shown in TablePrimitive when there are
 *     no rows; the design is moving toward always showing it as the
 *     header subtitle, so editing here is useful regardless).
 *   - Tags (chip-style; add by typing then Enter or comma; remove by X).
 *
 * Out of scope (separate task — flagged in the parent issue):
 *   - Row-level edits (add/remove/edit rows + row source_ref bbox).
 *   - Rewiring a row to a different document region.
 *
 * Rows are shown read-only so the user can see what's there.
 */
import { useEffect, useState } from "react";

import { LabelEditor } from "./LabelEditor";
import { usePatchNode } from "./_usePatchNode";
import type { EditorProps } from "./_types";

type Row = { key: string; value: string; source_ref?: { page?: number } };

export function SpecEditor({ workspaceSlug, node }: EditorProps) {
  const { patch, error } = usePatchNode(workspaceSlug, node.id);
  const data = node.data ?? {};
  const rows = (data.rows as Row[] | undefined) ?? [];

  const [description, setDescription] = useState((data.description as string | undefined) ?? "");
  const [tags, setTags] = useState<string[]>((data.tags as string[] | undefined) ?? []);
  const [tagDraft, setTagDraft] = useState("");

  useEffect(() => {
    setDescription((node.data?.description as string | undefined) ?? "");
    setTags((node.data?.tags as string[] | undefined) ?? []);
  }, [node.data, node.id]);

  const patchData = (override: Record<string, unknown>) => {
    patch({ data: { ...(node.data ?? {}), ...override } });
  };

  const addTag = (raw: string) => {
    const clean = raw.trim();
    if (!clean) return;
    if (tags.includes(clean)) { setTagDraft(""); return; }
    const next = [...tags, clean];
    setTags(next);
    setTagDraft("");
    patchData({ tags: next });
  };

  const removeTag = (t: string) => {
    const next = tags.filter((x) => x !== t);
    setTags(next);
    patchData({ tags: next });
  };

  return (
    <div className="flex flex-col gap-3">
      <LabelEditor workspaceSlug={workspaceSlug} node={node} />

      <div className="flex flex-col gap-1">
        <label htmlFor="spec-description" className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
          Description
        </label>
        <textarea
          id="spec-description"
          value={description}
          onChange={(e) => {
            const next = e.target.value;
            setDescription(next);
            patchData({ description: next });
          }}
          placeholder="What does this spec table describe?"
          rows={4}
          className="resize-y rounded border border-neutral-300 bg-white px-2 py-1.5 text-[12px] leading-snug outline-none focus:border-neutral-500"
        />
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
          Tags
        </span>
        <div className="flex flex-wrap items-center gap-1 rounded border border-neutral-300 bg-white p-1">
          {tags.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1 rounded bg-neutral-100 px-1.5 py-0.5 text-[11px] text-neutral-700"
            >
              {t}
              <button
                type="button"
                onClick={() => removeTag(t)}
                className="text-neutral-400 hover:text-neutral-700"
                aria-label={`remove tag ${t}`}
              >
                ×
              </button>
            </span>
          ))}
          <input
            type="text"
            value={tagDraft}
            onChange={(e) => {
              const next = e.target.value;
              if (next.endsWith(",")) {
                addTag(next.slice(0, -1));
              } else {
                setTagDraft(next);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addTag(tagDraft);
              } else if (e.key === "Backspace" && !tagDraft && tags.length > 0) {
                removeTag(tags[tags.length - 1]!);
              }
            }}
            placeholder={tags.length === 0 ? "Add tags…" : ""}
            className="min-w-[6rem] flex-1 bg-transparent px-1 py-0.5 text-[12px] outline-none"
          />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
          Rows ({rows.length}) <span className="ml-1 normal-case tracking-normal text-neutral-400">read-only</span>
        </span>
        {rows.length === 0 ? (
          <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[11px] text-neutral-400">
            No rows yet. Drag a region from a document onto the canvas to add one.
          </div>
        ) : (
          <ul className="divide-y divide-neutral-100 rounded border border-neutral-200">
            {rows.map((r, i) => (
              <li key={`${r.key}-${i}`} className="flex items-center justify-between gap-2 px-2 py-1 text-[12px]">
                <span className="truncate text-neutral-600">{r.key}</span>
                <span className="truncate text-neutral-900">{r.value}</span>
                <span className="shrink-0 text-[10px] text-neutral-400">
                  {r.source_ref?.page ? `p${r.source_ref.page}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error ? (
        <div className="rounded border border-red-300 bg-red-50 px-2 py-1 text-[11px] text-red-700">
          Save failed: {error}
        </div>
      ) : null}
    </div>
  );
}
