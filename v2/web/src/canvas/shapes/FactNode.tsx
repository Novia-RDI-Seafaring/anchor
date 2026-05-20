import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { Pictogram } from "@/canvas/icons";
import { useInlineField } from "@/canvas/useInlineField";

/**
 * FactNode — single-assertion card. Label + optional body text. Inline
 * rename is selection-gated; the body remains editable via the Properties
 * panel (see SpecEditor / LabelEditor) — kept off the canvas to avoid
 * double-editing the same text in two places.
 */
export function FactNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    text?: string;
    pictogram?: string;
    dashed?: boolean;
    width?: number;
    height?: number;
  };
  const label = d.label ?? "";
  const borderStyle = d.dashed ? "border-dashed" : "border-solid";
  const opacityClass = d.dashed ? "opacity-70" : "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
  });
  const wrapCursor = selected ? "cursor-move" : "cursor-pointer";
  return (
    <div
      className={`relative rounded-lg border ${borderStyle} border-neutral-400 bg-white px-3 py-2 text-sm shadow-sm ${opacityClass} ${wrapCursor}`}
      style={d.width && d.height ? { width: d.width, height: d.height } : { maxWidth: "20rem" }}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={120}
        minHeight={48}
        color="#0ea5e9"
      />
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
              className={`text-[11px] font-semibold uppercase tracking-wide text-neutral-600 ${selected ? "cursor-text" : "cursor-pointer"}`}
              onDoubleClick={(e) => {
                e.stopPropagation();
                rename.beginEdit();
              }}
              title={selected ? "double-click to rename" : undefined}
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
