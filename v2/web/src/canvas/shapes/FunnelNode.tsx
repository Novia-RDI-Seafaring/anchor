import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { Pictogram } from "@/canvas/icons";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * FunnelNode — diamond shape.
 *
 * Renders as a polygon-clipped div so the silhouette scales to any
 * width/height the user drags out. The previous implementation rotated an
 * inner rectangle 45° which only read as a diamond at a 1:1 aspect; at
 * 200×100 the rotated rect overflowed into a parallelogram. The new
 * approach is a single `clip-path: polygon(50% 0%, 100% 50%, 50% 100%,
 * 0% 50%)` — visually identical at square aspect and correct for any
 * stretched rhombus the user wants.
 *
 * The label sits inside the diamond's middle band (~50% of the height)
 * unrotated, constrained to ~70% width so text breaks inside the visible
 * area rather than spilling under the clipped corners.
 *
 * 4-corner NodeResizer with FREE aspect — drawing a 200×100 diamond is a
 * legitimate user gesture. Selection-gated inline rename. Empty label is
 * fine; the rail drops the node with no default label.
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
  const opacityClass = d.dashed ? "opacity-70" : "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
  });
  // Live-resize mirror — see ConceptNode for the rationale. Free aspect:
  // the rhombus can stretch to any width/height.
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const w = liveW ?? 96;
  const h = liveH ?? 96;
  const wrapCursor = selected ? "cursor-move" : "cursor-pointer";
  // Use a solid clipped polygon for the silhouette + an SVG polygon overlay
  // for the stroke so the dashed/solid border distinction stays crisp.
  // `clip-path` itself can't draw a border; the SVG layer carries the
  // stroke and respects `dashed` via stroke-dasharray.
  const strokeDash = d.dashed ? "6 4" : undefined;
  return (
    <div className={`relative ${wrapCursor} ${opacityClass}`} style={{ width: w, height: h }}>
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={48}
        minHeight={32}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <Handle type="target" position={Position.Left} />
      {/* Fill: a clipped div carries the white background + any flat fill
          tweaks future iterations want. */}
      <div
        className="absolute inset-0 bg-white"
        style={{
          clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)",
        }}
        aria-hidden
      />
      {/* Stroke: SVG polygon scales to any width/height without distortion
          via `preserveAspectRatio="none"` and gives us dashed/solid in CSS-
          like units. `vectorEffect="non-scaling-stroke"` keeps the stroke
          width perceptually constant at all sizes. */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden
      >
        <polygon
          points="50,0 100,50 50,100 0,50"
          fill="none"
          stroke="rgb(115 115 115)"
          strokeWidth="2"
          strokeDasharray={strokeDash}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      {/* Label sits in the diamond's central band — the widest part of the
          shape — and stays unrotated, in stark contrast to the previous
          rotated-rect trick where the label had to counter-rotate. ~70%
          width keeps wrapped text clear of the clipped corners. */}
      <div
        className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center text-xs font-medium leading-tight"
        style={{ padding: "0 15%" }}
      >
        {d.pictogram ? <Pictogram name={d.pictogram} className="text-neutral-700" /> : null}
        {rename.editing ? (
          <input
            {...rename.inputProps}
            className={`${rename.inputProps.className} w-[70%] rounded border border-neutral-300 bg-white px-1 py-0 text-center text-xs font-medium leading-tight outline-none focus:border-neutral-500`}
            placeholder="label"
          />
        ) : (
          <span
            className={`max-w-full break-words ${selected ? "cursor-text" : "cursor-pointer"}`}
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
