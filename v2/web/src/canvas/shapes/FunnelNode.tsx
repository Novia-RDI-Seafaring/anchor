import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { Pictogram } from "@/canvas/icons";
import { useInlineField } from "@/canvas/useInlineField";

/**
 * FunnelNode — diamond/funnel shape.
 *
 * Pure visual primitive: a CSS-rotated square that reads as a diamond on
 * the canvas. Label sits centred and unrotated. Optional pictogram glyph
 * picks up `data.pictogram`. Empty label is fine — the rail drops the node
 * with no default label and lets the user type one in via inline rename.
 *
 * Selection-gated inline rename + 4-corner NodeResizer.
 *
 * Underlying node_type string is `funnel` (kept for persistence stability
 * across the toolbar's "Diamond" rename); see canvas/registry.ts.
 */
export function FunnelNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    pictogram?: string;
    dashed?: boolean;
    width?: number;
    height?: number;
  };
  const label = d.label ?? "";
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed ? "opacity-70" : "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
  });
  const w = d.width ?? 96;
  const h = d.height ?? 96;
  const wrapCursor = selected ? "cursor-move" : "cursor-pointer";
  return (
    <div className={`relative ${wrapCursor}`} style={{ width: w, height: h }}>
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={48}
        minHeight={48}
        color="#0ea5e9"
      />
      <Handle type="target" position={Position.Left} />
      <div
        className={`absolute inset-2 rotate-45 border-2 ${borderStyle} border-neutral-500 bg-white ${opacityClass}`}
      />
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 px-2 text-center text-xs font-medium leading-tight">
        {d.pictogram ? <Pictogram name={d.pictogram} className="text-neutral-700" /> : null}
        {rename.editing ? (
          <input
            {...rename.inputProps}
            className={`${rename.inputProps.className} w-[4.5rem] rounded border border-neutral-300 bg-white px-1 py-0 text-center text-xs font-medium leading-tight outline-none focus:border-neutral-500`}
            placeholder="label"
          />
        ) : (
          <span
            className={`break-words ${selected ? "cursor-text" : "cursor-pointer"}`}
            onDoubleClick={(e) => {
              e.stopPropagation();
              rename.beginEdit();
            }}
            title={selected ? "double-click to rename" : undefined}
          >
            {label || <span className="text-neutral-400">untitled</span>}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
