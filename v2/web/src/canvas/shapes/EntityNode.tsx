import { Handle, Position, type NodeProps } from "@xyflow/react";

import { Pictogram } from "@/canvas/icons";

export function EntityNode({ data }: NodeProps) {
  const d = data as { label?: string; pictogram?: string; dashed?: boolean };
  const label = d.label ?? "entity";
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed ? "opacity-70" : "";
  return (
    <div
      className={`flex h-24 w-24 flex-col items-center justify-center gap-1 rounded-full border-2 ${borderStyle} border-neutral-500 bg-white text-xs font-medium ${opacityClass}`}
    >
      <Handle type="target" position={Position.Left} />
      {d.pictogram ? <Pictogram name={d.pictogram} className="text-neutral-700" /> : null}
      <span className="px-2 text-center leading-tight">{label}</span>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
