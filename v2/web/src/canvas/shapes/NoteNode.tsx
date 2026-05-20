import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { useInlineLabel } from "@/canvas/useInlineLabel";

/**
 * NoteNode — a sticky-note style text card. Renders `data.label` (one-line
 * heading) and `data.text` (body). No fancy markdown — paragraphs and line
 * breaks. Use these to annotate architecture diagrams, leave TODOs, or pin
 * descriptive prose alongside structural nodes.
 *
 * Inline rename covers the label today; editing the body is a follow-up
 * (left to a later PR — the existing TablePrimitive/spec flow already has
 * a richer text editor pattern we'll reuse).
 */
export function NoteNode({ id, data }: NodeProps) {
  const d = data as { label?: string; text?: string };
  const label = d.label ?? "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineLabel({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    label,
  });
  return (
    <div className="max-w-sm rounded-md border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-neutral-900 shadow-sm">
      <Handle type="target" position={Position.Left} />
      {rename.editing ? (
        <input
          {...rename.inputProps}
          className={`${rename.inputProps.className} w-full rounded border border-amber-300 bg-yellow-50 px-1 py-0 text-[11px] font-semibold uppercase tracking-wide text-amber-700 outline-none focus:border-amber-500`}
          placeholder="label"
        />
      ) : (
        <div
          className="cursor-text text-[11px] font-semibold uppercase tracking-wide text-amber-700"
          onDoubleClick={(e) => {
            e.stopPropagation();
            rename.beginEdit();
          }}
          title="double-click to rename"
        >
          {label || <span className="font-normal italic tracking-normal text-amber-500/70">untitled</span>}
        </div>
      )}
      {d.text ? (
        <div className="mt-1 whitespace-pre-wrap leading-snug">{d.text}</div>
      ) : null}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
