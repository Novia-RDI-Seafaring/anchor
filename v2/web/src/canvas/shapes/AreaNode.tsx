import { type NodeProps } from "@xyflow/react";

/**
 * AreaNode — labelled, dashed rounded-rectangle container.
 *
 * Renders a region with a title strip at the top, used to visually group
 * other nodes (subgraph). Set `data.label` for the title; `data.tone`
 * picks an accent style; `data.dashed` defaults to true (areas are always
 * dashed) but can be set to false for a solid container if needed.
 */
export function AreaNode({ data }: NodeProps) {
  const d = data as {
    label?: string;
    width?: number;
    height?: number;
    tone?: string;
    dashed?: boolean;
    subtitle?: string;
  };
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
  return (
    <div
      className={`pointer-events-auto rounded-xl border-2 ${borderStyle} ${tone}`}
      style={{ width: w, height: h }}
    >
      {d.label ? (
        <div className="border-b border-current/20 px-3 py-1.5">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-700">
            {d.label}
          </div>
          {d.subtitle ? (
            <div className="text-[10px] italic text-neutral-500">{d.subtitle}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
