/**
 * Palette — the "how do I add a node" surface.
 *
 * One row per shape type. Click to add at canvas centre; drag to drop at a
 * specific position. Either path issues a `POST /api/workspaces/{slug}/nodes`
 * with no special privilege beyond what an external agent has — the canvas
 * re-renders when SSE delivers `NodeAdded` back.
 */
import { useReactFlow } from "@xyflow/react";

import { canvases } from "@/api/canvases";

type ShapeSpec = {
  node_type: string;
  label: string;
  hint: string;
  width?: number;
  height?: number;
  data?: Record<string, unknown>;
};

const SHAPES: ShapeSpec[] = [
  { node_type: "concept", label: "Concept", hint: "generic textual node" },
  { node_type: "entity",  label: "Entity",  hint: "circular thing-of-substance" },
  { node_type: "fact",    label: "Fact",    hint: "single assertion" },
  { node_type: "note",    label: "Note",    hint: "free-form sticky" },
  { node_type: "area",    label: "Area",    hint: "dashed container", width: 360, height: 220 },
];

type Props = { workspaceSlug: string };

export function Palette({ workspaceSlug }: Props) {
  const { screenToFlowPosition } = useReactFlow();

  return (
    <div className="space-y-1">
      <div className="px-2 pt-1 pb-2 text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
        Shapes
      </div>
      {SHAPES.map((shape) => (
        <button
          key={shape.node_type}
          draggable
          onDragStart={(e) => {
            e.dataTransfer.effectAllowed = "copy";
            e.dataTransfer.setData(
              "application/x-anchor-node",
              JSON.stringify({
                node_type: shape.node_type,
                label: shape.label,
                ...(shape.width !== undefined ? { width: shape.width } : {}),
                ...(shape.height !== undefined ? { height: shape.height } : {}),
                data: shape.data ?? {},
              }),
            );
          }}
          onClick={async () => {
            // Click adds at the centre of the visible flow region (a sensible
            // default that doesn't require the user to know "drag, don't click").
            const center = screenToFlowPosition({
              x: window.innerWidth / 2,
              y: window.innerHeight / 2,
            });
            try {
              await canvases.addNode(workspaceSlug, {
                node_type: shape.node_type,
                label: shape.label,
                x: center.x,
                y: center.y,
                ...(shape.width !== undefined ? { width: shape.width } : {}),
                ...(shape.height !== undefined ? { height: shape.height } : {}),
                data: shape.data ?? {},
              });
            } catch (err) {
              // eslint-disable-next-line no-console
              console.error("addNode failed", err);
            }
          }}
          className="flex w-full cursor-grab items-center gap-2 rounded border border-neutral-200 bg-white px-2 py-1.5 text-left text-xs hover:bg-neutral-50 active:cursor-grabbing"
          title={shape.hint}
        >
          <ShapeGlyph type={shape.node_type} />
          <span className="font-medium text-neutral-800">{shape.label}</span>
          <span className="ml-auto text-[10px] text-neutral-400">{shape.hint}</span>
        </button>
      ))}
    </div>
  );
}

function ShapeGlyph({ type }: { type: string }) {
  const cls = "size-5 shrink-0 stroke-neutral-700";
  switch (type) {
    case "concept":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="3" y="6" width="18" height="12" rx="2" />
        </svg>
      );
    case "entity":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
    case "fact":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="4" y="6" width="16" height="12" rx="2" />
          <path d="M7 10h10M7 13h7" />
        </svg>
      );
    case "note":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <path d="M5 5h14v10l-4 4H5z" />
          <path d="M15 19v-4h4" />
        </svg>
      );
    case "area":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5} strokeDasharray="3 2">
          <rect x="3" y="5" width="18" height="14" rx="2" />
        </svg>
      );
  }
  return null;
}
