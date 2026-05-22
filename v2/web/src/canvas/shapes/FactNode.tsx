import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { resolveColors, resolveText } from "@/canvas/colors";
import { Pictogram } from "@/canvas/icons";
import { PlaceholderChip } from "@/canvas/PlaceholderChip";
import { placeholderState, PLACEHOLDER_BG, PLACEHOLDER_STROKE } from "@/canvas/placeholder";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * FactNode — single-assertion card. Label + optional body text. Inline
 * rename is selection-gated; the body remains editable via the Properties
 * panel (see SpecEditor / LabelEditor) — kept off the canvas to avoid
 * double-editing the same text in two places.
 */
export function FactNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    text?: string;
    pictogram?: string;
    dashed?: boolean;
    width?: number;
    height?: number;
    bg_color?: string;
    stroke_color?: string;
  };
  const label = d.label ?? "";
  const ph = placeholderState(d);
  const borderStyle = ph.active || d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed && !ph.active ? "opacity-70" : "";
  const baseColors = resolveColors(d);
  const bg = ph.active ? PLACEHOLDER_BG : baseColors.bg;
  const stroke = ph.active ? PLACEHOLDER_STROKE : baseColors.stroke;
  const t = resolveText(d);
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
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
      className={`relative rounded-lg border ${borderStyle} px-3 py-2 text-sm shadow-sm ${opacityClass} ${wrapCursor}`}
      style={{
        ...(liveW && liveH ? { width: liveW, height: liveH } : { maxWidth: "20rem" }),
        background: bg,
        borderColor: stroke,
        color: stroke,
      }}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={120}
        minHeight={48}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      {ph.active ? <PlaceholderChip hint={ph.hint} /> : null}
      <Handle type="target" position={Position.Left} />
      {/* Display label / body / pictogram inherit `color` from the wrapper
          (resolveColors → stroke). The edit-mode <input> keeps the
          original styling — recolouring an active text editor would be
          jarring. */}
      <div className="flex items-start gap-2">
        {d.pictogram ? <Pictogram name={d.pictogram} className="shrink-0 mt-0.5" /> : null}
        <div className="min-w-0">
          {rename.editing ? (
            <input
              {...rename.inputProps}
              className={`${rename.inputProps.className} w-full rounded border border-neutral-300 bg-white px-1 py-0 text-[11px] font-semibold uppercase tracking-wide text-neutral-600 outline-none focus:border-neutral-500`}
              placeholder="label"
            />
          ) : (
            <div
              className={`uppercase tracking-wide ${selected ? "cursor-text" : "cursor-pointer"}`}
              style={{
                color: t.color,
                fontWeight: Math.max(t.fontWeight, 600),
                textAlign: t.textAlign,
                fontFamily: t.fontFamily,
                fontSize: "11px",
              }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                rename.beginEdit();
              }}
              title={selected ? "double-click to rename" : undefined}
            >
              {label || <span className="font-normal italic tracking-normal opacity-50">untitled</span>}
            </div>
          )}
          {d.text ? (
            <div
              className="mt-1"
              style={{
                color: t.color,
                fontWeight: t.fontWeight,
                textAlign: t.textAlign,
                fontFamily: t.fontFamily,
                fontSize: t.fontSize,
              }}
            >
              {d.text}
            </div>
          ) : null}
        </div>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
