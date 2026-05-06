import { Handle, Position, type NodeProps } from "@xyflow/react";

/**
 * NoteNode — a sticky-note style text card. Renders `data.label` (one-line
 * heading) and `data.text` (body). No fancy markdown — paragraphs and line
 * breaks. Use these to annotate architecture diagrams, leave TODOs, or pin
 * descriptive prose alongside structural nodes.
 */
export function NoteNode({ data }: NodeProps) {
  const d = data as { label?: string; text?: string };
  return (
    <div className="max-w-sm rounded-md border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-neutral-900 shadow-sm">
      <Handle type="target" position={Position.Left} />
      {d.label ? (
        <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
          {d.label}
        </div>
      ) : null}
      {d.text ? (
        <div className="mt-1 whitespace-pre-wrap leading-snug">{d.text}</div>
      ) : null}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
