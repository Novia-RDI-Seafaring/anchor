import { Handle, Position, type NodeProps, type NodeTypes } from "@xyflow/react";
import { createContext, useContext, type ComponentType } from "react";
import { useParams } from "react-router-dom";

import { NodeSourceBadge } from "@/canvas/NodeSourceBadge";
import { ReviewBadge } from "@/canvas/ReviewBadge";
import { resolveColors, resolveText } from "@/canvas/colors";
import { cardSummary, compactDisplay } from "@/canvas/subtrees";
import { useInlineField } from "@/canvas/useInlineField";

export const CanvasStructureContext = createContext<{
  counts: Map<string, number>;
  readOnly?: boolean;
  toggle: (id: string) => void;
  inspect: (id: string) => void;
} | null>(null);

function CompactCard({ id, data, selected, type }: NodeProps) {
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({ workspaceSlug: workspaceSlug ?? "", nodeId: id,
    value: typeof data.label === "string" ? data.label : "", field: "label", canEdit: selected ?? false });
  const colors = resolveColors(data);
  const text = resolveText(data);
  const summary = cardSummary(data);
  return (
    <div data-testid="compact-card" className="relative w-64 rounded-lg border px-3 py-2 shadow-sm"
      style={{ background: colors.bg, borderColor: colors.stroke, color: text.color, fontFamily: text.fontFamily }}>
      <Handle type="target" position={Position.Left} />
      <ReviewBadge data={data} nodeId={id} />
      {rename.editing ? <input {...rename.inputProps} aria-label="Node label" className="w-full border bg-white px-1" />
        : <div className="truncate font-semibold" style={{ fontSize: text.fontSize }}>
          {typeof data.label === "string" && data.label ? data.label : `untitled ${type}`}
        </div>}
      {summary ? <div className="truncate text-xs text-neutral-500" title={summary}>{summary}</div> : null}
      {/* Row endpoints survive compact display, keeping existing evidence wiring. */}
      {type === "spec" && Array.isArray(data.rows) ? data.rows.map((row, i) => (
        <Handle key={i} type="source" position={Position.Right}
          id={`row:${i}:${String(row && typeof row === "object" ? (row as { key?: unknown }).key ?? "" : "").trim()}`}
          style={{ opacity: 0, pointerEvents: "none", top: "50%" }} />
      )) : null}
      <Handle type="source" position={Position.Right} />
      <NodeSourceBadge data={data} workspaceSlug={workspaceSlug} />
    </div>
  );
}

const wrapped = new Map<ComponentType<NodeProps>, ComponentType<NodeProps>>();
export function structuredNodeTypes(base: NodeTypes): NodeTypes {
  return new Proxy(base, {
    get(target, key: string) {
      const Renderer = target[key];
      if (!Renderer) return undefined;
      if (!wrapped.has(Renderer)) {
        const Structured = (props: NodeProps) => {
          const structure = useContext(CanvasStructureContext);
          const count = structure?.counts.get(props.id) ?? 0;
          const collapsed = props.data.collapsed === true;
          const compact = compactDisplay(props.type, props.data);
          return (
            <div className="relative" onDoubleClick={() => {
              if (!structure?.readOnly && (props.type === "document" || props.type === "canvas")) return;
              structure?.inspect(props.id);
            }}>
              {compact ? <CompactCard {...props} /> : <Renderer {...props} />}
              {!structure?.readOnly ? <div className="nodrag nopan absolute -top-5 right-0 flex gap-1">
                {count > 0 || collapsed ? <button type="button"
                  className="rounded border border-neutral-300 bg-white px-1.5 text-[11px] text-neutral-700 shadow-sm"
                  aria-label={`${collapsed ? "Expand" : "Collapse"} subtree`}
                  aria-expanded={!collapsed}
                  onDoubleClick={(event) => event.stopPropagation()}
                  onClick={(event) => { event.stopPropagation(); structure?.toggle(props.id); }}>
                  {collapsed ? `+${count}` : "-"}
                </button> : null}
                {props.selected ? <button type="button"
                  className="rounded border border-neutral-300 bg-white px-1.5 text-[11px] text-neutral-700 shadow-sm"
                  onDoubleClick={(event) => event.stopPropagation()}
                  onClick={(event) => { event.stopPropagation(); structure?.inspect(props.id); }}>Details</button> : null}
              </div> : null}
            </div>
          );
        };
        wrapped.set(Renderer, Structured);
      }
      return wrapped.get(Renderer);
    },
  });
}
