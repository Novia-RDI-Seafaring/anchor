import { NodeResizer, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * AreaNode — labelled, dashed rounded-rectangle container.
 *
 * Renders a region with a title strip at the top, used to visually group
 * other nodes (subgraph). Set `data.label` for the title; `data.tone`
 * picks an accent style; `data.dashed` defaults to true (areas are always
 * dashed) but can be set to false for a solid container if needed.
 *
 * Areas use the rail's drag-out width/height by default but resize freely
 * via NodeResizer once placed. Inline rename is selection-gated.
 *
 * Note: ReactFlow renders areas with `selectable: false` (see
 * `CanvasGraph.toRfNode`) so they sit behind other nodes. The
 * `NodeResizer` runs off the `selected` prop, which is still set by
 * ReactFlow even though the area can't be picked by drag-rectangle. For
 * the resize handles to appear, callers will need to set `selectable:
 * true` on areas in a follow-up; for now the area lives at its drop-time
 * size and resizes via the Properties panel.
 */
export function AreaNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    width?: number;
    height?: number;
    tone?: string;
    dashed?: boolean;
    subtitle?: string;
  };
  const label = d.label ?? "";
  // Live-resize mirror — see ConceptNode for the rationale.
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const w = liveW ?? 320;
  const h = liveH ?? 200;
  const dashed = d.dashed !== false;
  const toneClass: Record<string, string> = {
    sources: "border-neutral-500/70 bg-neutral-50",
    producers: "border-neutral-500/70 bg-neutral-50",
    durable: "border-neutral-500/70 bg-neutral-50",
    consumers: "border-neutral-500/70 bg-neutral-50",
    core: "border-neutral-500/70 bg-neutral-50",
    default: "border-neutral-400 bg-white/40",
  };
  const tone = toneClass[d.tone ?? "default"] ?? toneClass.default;
  const borderStyle = dashed ? "border-dashed" : "border-solid";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
  });
  return (
    <div
      className={`pointer-events-auto rounded-xl border-2 ${borderStyle} ${tone}`}
      style={{ width: w, height: h }}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={120}
        minHeight={60}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <div className="border-b border-current/20 px-3 py-1.5">
        {rename.editing ? (
          <input
            {...rename.inputProps}
            className={`${rename.inputProps.className} w-full rounded border border-neutral-300 bg-white px-1 py-0 text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-700 outline-none focus:border-neutral-500`}
            placeholder="label"
          />
        ) : (
          <div
            className={`text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-700 ${selected ? "cursor-text" : "cursor-pointer"}`}
            onDoubleClick={(e) => {
              e.stopPropagation();
              rename.beginEdit();
            }}
            title={selected ? "double-click to rename" : undefined}
          >
            {label || <span className="font-normal italic tracking-normal text-neutral-400">untitled · double-click to name</span>}
          </div>
        )}
        {d.subtitle ? (
          <div className="text-[10px] italic text-neutral-500">{d.subtitle}</div>
        ) : null}
      </div>
    </div>
  );
}
