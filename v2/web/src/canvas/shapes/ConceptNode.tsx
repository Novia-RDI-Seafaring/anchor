import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { resolveColors } from "@/canvas/colors";
import { Pictogram } from "@/canvas/icons";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * ConceptNode — rounded rectangle shape.
 *
 * Selection-gated editing: `data.label` becomes editable only when the
 * node is `selected` (draw.io style). 8-handle resize via NodeResizer
 * appears on selection too.
 */
export function ConceptNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    pictogram?: string;
    dashed?: boolean;
    subtitle?: string;
    width?: number;
    height?: number;
    bg_color?: string;
    stroke_color?: string;
  };
  const label = d.label ?? "";
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed ? "opacity-70" : "";
  const { bg, stroke } = resolveColors(d);
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
  });
  // Live-resize mirror: while NodeResizer drags, `width`/`height` track the
  // pointer in real time; `data.*` is only written on resize-end. Without
  // this the inner div stays at its persisted size mid-drag (bug).
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  // Cursor: text when selected (hint at edit), move when selected (drag),
  // pointer when unselected. Move wins on the wrapper; the label area gets
  // text via `cursor-text` below.
  const wrapCursor = selected ? "cursor-move" : "cursor-pointer";
  return (
    <div
      className={`relative rounded-lg border ${borderStyle} px-3 py-2 text-sm shadow-sm ${opacityClass} ${wrapCursor}`}
      style={{
        ...(liveW && liveH ? { width: liveW, height: liveH } : {}),
        background: bg,
        borderColor: stroke,
        color: stroke,
      }}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={80}
        minHeight={32}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <Handle type="target" position={Position.Left} />
      {/* Label / pictogram inherit `color` from the wrapper above (resolveColors
          → stroke). Removing the hardcoded `text-neutral-*` classes lets the
          Style picker's stroke colour drive the text. */}
      <div className="flex items-center gap-2">
        {d.pictogram ? <Pictogram name={d.pictogram} className="shrink-0" /> : null}
        <div className="min-w-0">
          {rename.editing ? (
            <input
              {...rename.inputProps}
              className={`${rename.inputProps.className} w-full min-w-[6rem] truncate rounded border border-neutral-300 bg-white px-1 py-0 text-sm font-medium leading-tight outline-none focus:border-neutral-500`}
              placeholder="label"
            />
          ) : (
            <div
              className={`truncate font-medium leading-tight ${selected ? "cursor-text" : "cursor-pointer"}`}
              onDoubleClick={(e) => {
                e.stopPropagation();
                rename.beginEdit();
              }}
              title={selected ? "double-click to rename" : undefined}
            >
              {label || <span className="text-neutral-400">untitled</span>}
            </div>
          )}
          {d.subtitle ? (
            <div className="truncate text-[11px] italic text-neutral-500 leading-tight">
              {d.subtitle}
            </div>
          ) : null}
        </div>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
