import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { Pictogram } from "@/canvas/icons";
import { useInlineLabel } from "@/canvas/useInlineLabel";

export function FactNode({ id, data }: NodeProps) {
  const d = data as { label?: string; text?: string; pictogram?: string; dashed?: boolean };
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
    <div
      className={`max-w-xs rounded-lg border ${borderStyle} border-neutral-400 bg-white px-3 py-2 text-sm shadow-sm ${opacityClass}`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-start gap-2">
        {d.pictogram ? <Pictogram name={d.pictogram} className="text-neutral-700 shrink-0 mt-0.5" /> : null}
        <div className="min-w-0">
          {rename.editing ? (
            <input
              {...rename.inputProps}
              className={`${rename.inputProps.className} w-full rounded border border-neutral-300 bg-white px-1 py-0 text-[11px] font-semibold uppercase tracking-wide text-neutral-600 outline-none focus:border-neutral-500`}
              placeholder="label"
            />
          ) : (
            <div
              className="cursor-text text-[11px] font-semibold uppercase tracking-wide text-neutral-600"
              onDoubleClick={(e) => {
                e.stopPropagation();
                rename.beginEdit();
              }}
              title="double-click to rename"
            >
              {label || <span className="font-normal italic tracking-normal text-neutral-400">untitled</span>}
            </div>
          )}
          {d.text ? <div className="mt-1 text-neutral-800">{d.text}</div> : null}
        </div>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
