import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { Pictogram } from "@/canvas/icons";
import { useInlineLabel } from "@/canvas/useInlineLabel";

/**
 * FunnelNode — diamond/funnel shape.
 *
 * Pure visual primitive: a CSS-rotated square that reads as a diamond on
 * the canvas. Label sits centred and unrotated. Optional pictogram glyph
 * picks up `data.pictogram`. Empty label is fine — toolbar drops the node
 * with no default label and lets the user type one in via inline rename.
 *
 * Underlying node_type string is `funnel` (kept for persistence stability
 * across the toolbar's "Diamond" rename); see canvas/registry.ts.
 */
export function FunnelNode({ id, data }: NodeProps) {
  const d = data as { label?: string; pictogram?: string; dashed?: boolean };
  const label = d.label ?? "";
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed ? "opacity-70" : "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineLabel({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    label,
  });
  return (
    <div className="relative h-24 w-24">
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
            className="cursor-text break-words"
            onDoubleClick={(e) => {
              e.stopPropagation();
              rename.beginEdit();
            }}
            title="double-click to rename"
          >
            {label || <span className="text-neutral-400">untitled</span>}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
