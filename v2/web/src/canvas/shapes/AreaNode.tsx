import { type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { useInlineLabel } from "@/canvas/useInlineLabel";

/**
 * AreaNode — labelled, dashed rounded-rectangle container.
 *
 * Renders a region with a title strip at the top, used to visually group
 * other nodes (subgraph). Set `data.label` for the title; `data.tone`
 * picks an accent style; `data.dashed` defaults to true (areas are always
 * dashed) but can be set to false for a solid container if needed.
 *
 * Empty label is allowed (toolbar drops produce an empty-labelled area
 * that the user titles via the inline rename below). The title strip is
 * always rendered so there's a visible affordance to double-click.
 */
export function AreaNode({ id, data }: NodeProps) {
  const d = data as {
    label?: string;
    width?: number;
    height?: number;
    tone?: string;
    dashed?: boolean;
    subtitle?: string;
  };
  const label = d.label ?? "";
  const w = d.width ?? 320;
  const h = d.height ?? 200;
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
  const rename = useInlineLabel({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    label,
  });
  return (
    <div
      className={`pointer-events-auto rounded-xl border-2 ${borderStyle} ${tone}`}
      style={{ width: w, height: h }}
    >
      <div className="border-b border-current/20 px-3 py-1.5">
        {rename.editing ? (
          <input
            {...rename.inputProps}
            className={`${rename.inputProps.className} w-full rounded border border-neutral-300 bg-white px-1 py-0 text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-700 outline-none focus:border-neutral-500`}
            placeholder="label"
          />
        ) : (
          <div
            className="cursor-text text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-700"
            onDoubleClick={(e) => {
              e.stopPropagation();
              rename.beginEdit();
            }}
            title="double-click to rename"
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
