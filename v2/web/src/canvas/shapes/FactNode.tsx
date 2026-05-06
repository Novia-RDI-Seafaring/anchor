import { Handle, Position, type NodeProps } from "@xyflow/react";

import { Pictogram } from "@/canvas/icons";

export function FactNode({ data }: NodeProps) {
  const d = data as { label?: string; text?: string; pictogram?: string; dashed?: boolean };
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed ? "opacity-70" : "";
  return (
    <div
      className={`max-w-xs rounded-lg border ${borderStyle} border-neutral-400 bg-white px-3 py-2 text-sm shadow-sm ${opacityClass}`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-start gap-2">
        {d.pictogram ? <Pictogram name={d.pictogram} className="text-neutral-700 shrink-0 mt-0.5" /> : null}
        <div className="min-w-0">
          {d.label ? (
            <div className="text-[11px] font-semibold uppercase tracking-wide text-neutral-600">
              {d.label}
            </div>
          ) : null}
          {d.text ? <div className="mt-1 text-neutral-800">{d.text}</div> : null}
        </div>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
