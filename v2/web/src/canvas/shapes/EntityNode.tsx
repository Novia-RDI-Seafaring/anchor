import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { resolveColors } from "@/canvas/colors";
import { Pictogram } from "@/canvas/icons";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * EntityNode — circular shape.
 *
 * Resize is square-only (`keepAspectRatio`) so the shape stays a circle no
 * matter which handle the user drags. Inline rename is selection-gated.
 */
export function EntityNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    pictogram?: string;
    dashed?: boolean;
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
  // Live-resize mirror — see ConceptNode for the rationale. Circle stays
  // 1:1 thanks to NodeResizer's `keepAspectRatio`, so width === height.
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const size = liveW ?? liveH ?? 96; // 24*4 → h-24 default
  const wrapCursor = selected ? "cursor-move" : "cursor-pointer";
  return (
    <div
      className={`relative flex flex-col items-center justify-center gap-1 rounded-full border-2 ${borderStyle} text-xs font-medium ${opacityClass} ${wrapCursor}`}
      style={{
        width: size,
        height: size,
        background: bg,
        borderColor: stroke,
        color: stroke,
      }}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={48}
        minHeight={48}
        keepAspectRatio
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <Handle type="target" position={Position.Left} />
      {/* Pictogram inherits `color` from the wrapper — see ConceptNode for
          the rationale. */}
      {d.pictogram ? <Pictogram name={d.pictogram} /> : null}
      {rename.editing ? (
        <input
          {...rename.inputProps}
          className={`${rename.inputProps.className} w-[5rem] rounded border border-neutral-300 bg-white px-1 py-0 text-center text-xs font-medium leading-tight outline-none focus:border-neutral-500`}
          placeholder="label"
        />
      ) : (
        <span
          className={`px-2 text-center leading-tight ${selected ? "cursor-text" : "cursor-pointer"}`}
          onDoubleClick={(e) => {
            e.stopPropagation();
            rename.beginEdit();
          }}
          title={selected ? "double-click to rename" : undefined}
        >
          {label || <span className="text-neutral-400">untitled</span>}
        </span>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
