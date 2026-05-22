import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * NoteNode — a sticky-note style text card. Renders `data.label` (one-line
 * heading) and `data.text` (multi-line body). The body is a free-form text
 * area: paragraphs and line breaks. Use these to annotate architecture
 * diagrams, leave TODOs, or pin descriptive prose alongside structural
 * nodes.
 *
 * Two independent inline editors (both selection-gated):
 *   - Label  (single-line) — double-click the title strip. Enter commits.
 *   - Body   (multi-line)  — double-click the body region. Enter commits,
 *     Shift+Enter inserts a newline, Esc cancels, blur commits. Empty body
 *     is fine; an explicit hint nudges the user to start typing.
 *
 * 8-handle NodeResizer appears on selection.
 */
export function NoteNode({ id, data, selected }: NodeProps) {
  const d = data as { label?: string; text?: string; width?: number; height?: number };
  const label = d.label ?? "";
  const text = d.text ?? "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
  });
  const body = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: text,
    field: "text",
    multiline: true,
    canEdit: selected ?? false,
  });
  // Live-resize mirror — see ConceptNode for the rationale.
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const wrapCursor = selected ? "cursor-move" : "cursor-pointer";
  return (
    <div
      className={`relative max-w-sm rounded-md border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-neutral-900 shadow-sm ${wrapCursor}`}
      style={liveW && liveH ? { width: liveW, height: liveH, maxWidth: "none" } : undefined}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={120}
        minHeight={48}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <Handle type="target" position={Position.Left} />
      {rename.editing ? (
        <input
          {...rename.inputProps}
          className={`${rename.inputProps.className} w-full rounded border border-amber-300 bg-yellow-50 px-1 py-0 text-[11px] font-semibold uppercase tracking-wide text-amber-700 outline-none focus:border-amber-500`}
          placeholder="label"
        />
      ) : (
        <div
          className={`text-[11px] font-semibold uppercase tracking-wide text-amber-700 ${selected ? "cursor-text" : "cursor-pointer"}`}
          onDoubleClick={(e) => {
            e.stopPropagation();
            rename.beginEdit();
          }}
          title={selected ? "double-click to rename" : undefined}
        >
          {label || <span className="font-normal italic tracking-normal text-amber-500/70">untitled</span>}
        </div>
      )}
      {body.editing ? (
        <textarea
          {...body.inputProps}
          className={`${body.inputProps.className} mt-1 w-full min-h-[3rem] resize-y rounded border border-amber-300 bg-yellow-50/80 px-1 py-0.5 leading-snug text-neutral-900 outline-none focus:border-amber-500`}
          placeholder="note body — Shift+Enter for newline, Enter to commit"
        />
      ) : text ? (
        <div
          className={`mt-1 whitespace-pre-wrap leading-snug ${selected ? "cursor-text" : "cursor-pointer"}`}
          onDoubleClick={(e) => {
            e.stopPropagation();
            body.beginEdit();
          }}
          title={selected ? "double-click to edit" : undefined}
        >
          {text}
        </div>
      ) : (
        <div
          className={`mt-1 italic text-amber-500/70 leading-snug ${selected ? "cursor-text" : "cursor-pointer"}`}
          onDoubleClick={(e) => {
            e.stopPropagation();
            body.beginEdit();
          }}
          title={selected ? "double-click to edit" : undefined}
        >
          {selected ? "double-click to add body" : "(empty note)"}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
