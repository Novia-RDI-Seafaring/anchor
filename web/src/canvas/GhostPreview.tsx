/**
 * GhostPreview — read-only overlay of a suggestion's staged ops (#344).
 *
 * When the thread panel selects a suggestion, its `ops` are projected onto
 * the canvas without touching it: added nodes as dashed outlines at their
 * proposed positions (client ids resolve edge endpoints), removed nodes
 * dimmed with a strike, updated nodes with a diff badge (old → new label),
 * added edges dashed, removed edges dimmed. Clears when the suggestion is
 * deselected. The mental model is a pull-request diff drawn in place: the
 * user's sketch never moves until they approve.
 *
 * Invariant: this component reads the workspace store and the threads
 * store and writes to neither; it imports no API module. Screen-space
 * fixed positioning (like NodeContextToolbar), `pointer-events: none`.
 */
import { useMemo } from "react";

import { useCanvasStore } from "@/stores/canvasStore";
import {
  findItem,
  ghostElementsFromOps,
  type GhostEdge,
  type GhostNode,
} from "@/threads/threads";
import { useThreadsStore } from "@/threads/threadsStore";

import { useFlowToScreen } from "./useFlowToScreen";

const ADDED = "#10b981"; // emerald-500
const REMOVED = "#9ca3af"; // gray-400
const UPDATED = "#f59e0b"; // amber-500

export function GhostPreview() {
  const previewItemId = useThreadsStore((s) => s.previewItemId);
  const thread = useThreadsStore((s) => s.thread);
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const { toScreen, zoom } = useFlowToScreen();

  const item = findItem(thread, previewItemId);
  const elements = useMemo(
    () => (item && Array.isArray(item.ops) ? ghostElementsFromOps(item.ops, nodes, edges) : null),
    [item, nodes, edges],
  );

  if (!elements || !item) return null;

  return (
    <div
      aria-hidden
      data-testid="ghost-preview"
      data-item-id={item.id}
      style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 25 }}
    >
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
        {elements.edges
          .filter((e) => !e.missing)
          .map((e) => (
            <GhostEdgeLine key={`${e.kind}-${e.id}`} edge={e} toScreen={toScreen} />
          ))}
      </svg>
      {elements.nodes
        .filter((n) => !n.missing)
        .map((n) => (
          <GhostNodeBox key={`${n.kind}-${n.id}`} node={n} toScreen={toScreen} zoom={zoom} />
        ))}
    </div>
  );
}

function GhostNodeBox({
  node,
  toScreen,
  zoom,
}: {
  node: GhostNode;
  toScreen: (p: { x: number; y: number }) => { x: number; y: number };
  zoom: number;
}) {
  const tl = toScreen({ x: node.rect.x, y: node.rect.y });
  const width = Math.max(node.rect.width * zoom, 8);
  const height = Math.max(node.rect.height * zoom, 8);
  const base: React.CSSProperties = {
    position: "absolute",
    left: tl.x,
    top: tl.y,
    width,
    height,
    borderRadius: 8,
    boxSizing: "border-box",
  };
  if (node.kind === "node-added") {
    return (
      <div
        data-testid="ghost-node"
        data-ghost-kind="node-added"
        data-node-id={node.id}
        style={{
          ...base,
          border: `2px dashed ${ADDED}`,
          background: "rgba(16, 185, 129, 0.08)",
        }}
      >
        <span
          className="absolute -top-2.5 left-2 rounded-full bg-white px-1.5 py-0.5 text-[10px] italic shadow-sm"
          style={{ color: ADDED, border: `1px solid ${ADDED}` }}
        >
          + {node.node_type}
        </span>
        <span className="block truncate px-2 py-1 text-[11px]" style={{ color: ADDED }}>
          {node.label}
        </span>
      </div>
    );
  }
  if (node.kind === "node-removed") {
    return (
      <div
        data-testid="ghost-node"
        data-ghost-kind="node-removed"
        data-node-id={node.id}
        style={{
          ...base,
          border: `2px solid ${REMOVED}`,
          background: "rgba(255, 255, 255, 0.7)",
        }}
      >
        <span
          className="absolute -top-2.5 left-2 rounded-full bg-white px-1.5 py-0.5 text-[10px] italic line-through shadow-sm"
          style={{ color: REMOVED, border: `1px solid ${REMOVED}` }}
        >
          − {node.label || node.id}
        </span>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "50%",
            height: 2,
            background: REMOVED,
            transform: "rotate(-8deg)",
          }}
        />
      </div>
    );
  }
  return (
    <div
      data-testid="ghost-node"
      data-ghost-kind="node-updated"
      data-node-id={node.id}
      style={{ ...base, border: `2px dashed ${UPDATED}` }}
    >
      <span
        data-testid="ghost-diff-badge"
        className="absolute -top-2.5 left-2 max-w-full truncate rounded-full bg-white px-1.5 py-0.5 text-[10px] italic shadow-sm"
        style={{ color: UPDATED, border: `1px solid ${UPDATED}` }}
      >
        {node.oldLabel !== undefined
          ? `${node.oldLabel || "(empty)"} → ${node.label || "(empty)"}`
          : `~ ${(node.fields ?? []).join(", ") || "updated"}`}
      </span>
    </div>
  );
}

function GhostEdgeLine({
  edge,
  toScreen,
}: {
  edge: GhostEdge;
  toScreen: (p: { x: number; y: number }) => { x: number; y: number };
}) {
  const a = toScreen(edge.from);
  const b = toScreen(edge.to);
  const color = edge.kind === "edge-added" ? ADDED : edge.kind === "edge-removed" ? REMOVED : UPDATED;
  return (
    <g data-testid="ghost-edge" data-ghost-kind={edge.kind} data-edge-id={edge.id}>
      <line
        x1={a.x}
        y1={a.y}
        x2={b.x}
        y2={b.y}
        stroke={color}
        strokeWidth={2}
        strokeDasharray={edge.kind === "edge-removed" ? undefined : "6 4"}
        opacity={edge.kind === "edge-removed" ? 0.5 : 1}
      />
      {edge.label ? (
        <text
          x={(a.x + b.x) / 2}
          y={(a.y + b.y) / 2 - 4}
          fill={color}
          fontSize={10}
          textAnchor="middle"
          style={{ fontStyle: "italic" }}
        >
          {edge.label}
        </text>
      ) : null}
    </g>
  );
}
