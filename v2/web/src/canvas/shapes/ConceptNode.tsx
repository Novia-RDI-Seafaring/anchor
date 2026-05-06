import { Handle, Position, type NodeProps } from "@xyflow/react";

import { Pictogram } from "@/canvas/icons";

export function ConceptNode({ data }: NodeProps) {
  const d = data as { label?: string; pictogram?: string; dashed?: boolean; subtitle?: string };
  const label = d.label ?? "concept";
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed ? "opacity-70" : "";
  return (
    <div
      className={`rounded-lg border ${borderStyle} border-neutral-400 bg-white px-3 py-2 text-sm shadow-sm ${opacityClass}`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center gap-2 text-neutral-900">
        {d.pictogram ? <Pictogram name={d.pictogram} className="text-neutral-700 shrink-0" /> : null}
        <div className="min-w-0">
          <div className="truncate font-medium leading-tight">{label}</div>
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
