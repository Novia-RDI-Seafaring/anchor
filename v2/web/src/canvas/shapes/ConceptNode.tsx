import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { Pictogram } from "@/canvas/icons";
import { useInlineLabel } from "@/canvas/useInlineLabel";

export function ConceptNode({ id, data }: NodeProps) {
  const d = data as { label?: string; pictogram?: string; dashed?: boolean; subtitle?: string };
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
      className={`rounded-lg border ${borderStyle} border-neutral-400 bg-white px-3 py-2 text-sm shadow-sm ${opacityClass}`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center gap-2 text-neutral-900">
        {d.pictogram ? <Pictogram name={d.pictogram} className="text-neutral-700 shrink-0" /> : null}
        <div className="min-w-0">
          {rename.editing ? (
            <input
              {...rename.inputProps}
              className={`${rename.inputProps.className} w-full min-w-[6rem] truncate rounded border border-neutral-300 bg-white px-1 py-0 text-sm font-medium leading-tight outline-none focus:border-neutral-500`}
              placeholder="label"
            />
          ) : (
            <div
              className="cursor-text truncate font-medium leading-tight"
              onDoubleClick={(e) => {
                e.stopPropagation();
                rename.beginEdit();
              }}
              title="double-click to rename"
            >
              {label || <span className="text-neutral-400">untitled</span>}
            </div>
          )}
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
