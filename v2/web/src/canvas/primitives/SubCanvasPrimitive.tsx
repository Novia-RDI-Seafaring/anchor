/**
 * SubCanvasPrimitive — a representational link from one canvas to another.
 *
 * The tile shows an abstract glyph + the child canvas's title + a
 * "N nodes · M edges" line. We deliberately do NOT load the child's PNG
 * snapshot inline: the parent canvas may hold a dozen sub-canvas tiles
 * and pulling on a Chromium snapshotter for each of them was both slow
 * and visually noisy. The user drills in by double-clicking — that's
 * where the full canvas lives.
 *
 * Counts come from the shared `useWorkspacesList()` cache (one GET
 * /api/workspaces per page rather than one per tile). If the cache hasn't
 * landed yet the tile shows a soft "…" placeholder.
 *
 * Renderer responsibilities:
 *   - Show a 240x160 tile with the child's title (or slug), the graph
 *     glyph, and the node/edge counts.
 *   - Surface a "↩ already visiting" badge when the child slug is already
 *     in the user's breadcrumb chain — cycle prevention, see breadcrumb.ts.
 *     Double-click is disabled in that case.
 *   - Inline-rename edits `data.title` only — the `canvas_slug` is the
 *     link key and must stay stable.
 *
 * Navigation lives in CanvasGraph.tsx's `onNodeDoubleClick` (see there).
 * This primitive only renders.
 */
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useEffect } from "react";
import { useParams } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { breadcrumb } from "@/canvas/breadcrumb";
import { useInlineField } from "@/canvas/useInlineField";
import { useWorkspacesList } from "@/canvas/useWorkspacesList";

type SubCanvasData = {
  canvas_slug?: string;
  title?: string;
  label?: string;
};

/** Tiny self-contained graph glyph — three nodes joined by two edges. */
function GraphGlyph({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      aria-hidden
    >
      <line x1="5" y1="5" x2="14" y2="10" />
      <line x1="14" y1="10" x2="6" y2="15" />
      <circle cx="5" cy="5" r="2" fill="white" />
      <circle cx="14" cy="10" r="2" fill="white" />
      <circle cx="6" cy="15" r="2" fill="white" />
    </svg>
  );
}

export function SubCanvasPrimitive({ id, data, selected }: NodeProps) {
  const d = (data ?? {}) as SubCanvasData;
  const subSlug = d.canvas_slug ?? "";
  const title = d.title ?? d.label ?? subSlug;
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const snap = useWorkspacesList();
  const child = subSlug ? snap?.bySlug.get(subSlug) : undefined;

  // Whether this link points to a canvas already in the breadcrumb chain.
  // If so, double-click is disabled (cycle prevention) and we show a
  // badge so the user understands why.
  const inChain = subSlug ? breadcrumb.includes(subSlug) : false;

  // The inline-edit hook only edits the *title*. canvas_slug is the link
  // and must remain stable so navigation keeps working.
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: title,
    field: "title",
    canEdit: selected ?? false,
  });

  // Cascade-rename: whenever the tile's `data.title` differs from the
  // CHILD workspace's stored `meta.title`, push the new title to the
  // child via PATCH /api/workspaces/<child>. Without this, the tile
  // displays the renamed title but the landing-page folder tree, the
  // breadcrumbs, and any other view of the child canvas still show
  // "Sub-canvas". The rename API is idempotent (no-op on equal titles),
  // so this effect is safe to fire on every render. We swallow errors;
  // SSE / next list refresh reconciles eventually.
  useEffect(() => {
    if (!subSlug) return;
    if (!d.title) return;
    if (child && child.title === d.title) return;
    canvases.rename(subSlug, d.title).catch(() => {});
  }, [subSlug, d.title, child]);

  return (
    <div
      className={`relative w-[240px] overflow-hidden rounded-lg border-2 bg-white text-sm shadow-sm transition hover:shadow-md ${
        selected ? "border-sky-500 ring-2 ring-sky-200" : "border-neutral-300"
      }`}
      style={{ height: 160 }}
      title={subSlug ? `sub-canvas → ${subSlug}` : "sub-canvas (unlinked)"}
    >
      <Handle type="target" position={Position.Left} />

      {/* Header — title + drill-down hint. */}
      <div className="flex items-center justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1">
        <div className="flex min-w-0 items-baseline gap-1.5">
          <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-neutral-500">
            canvas
          </span>
          {rename.editing ? (
            <input
              {...rename.inputProps}
              className={`${rename.inputProps.className} min-w-0 flex-1 truncate rounded border border-neutral-300 bg-white px-1 py-0 text-[12px] font-medium leading-tight outline-none focus:border-neutral-500`}
              placeholder="title"
            />
          ) : (
            <div
              className={`truncate text-[12px] font-medium leading-tight text-neutral-800 ${
                selected ? "cursor-text" : "cursor-pointer"
              }`}
              onDoubleClick={(e) => {
                e.stopPropagation();
                rename.beginEdit();
              }}
              title={selected ? "double-click to rename" : undefined}
            >
              {title || <span className="text-neutral-400">untitled</span>}
            </div>
          )}
        </div>
        <span aria-hidden className="ml-1 shrink-0 text-neutral-400">
          →
        </span>
      </div>

      {/* Body — abstract representation: glyph + stats. */}
      <div className="nodrag nopan relative flex h-[112px] w-full flex-col items-center justify-center gap-1.5 bg-gradient-to-br from-neutral-50 to-neutral-100">
        <GraphGlyph className="size-9 text-neutral-400" />
        <div className="text-[11px] text-neutral-600">
          {child ? (
            <>
              <span className="font-medium text-neutral-800">{child.node_count}</span>{" "}
              <span className="text-neutral-500">node{child.node_count === 1 ? "" : "s"}</span>
              <span className="px-1 text-neutral-400">·</span>
              <span className="font-medium text-neutral-800">{child.edge_count}</span>{" "}
              <span className="text-neutral-500">edge{child.edge_count === 1 ? "" : "s"}</span>
            </>
          ) : (
            <span className="text-neutral-400">…</span>
          )}
        </div>
        <div className="text-[10px] text-neutral-400">{subSlug || "unlinked"}</div>

        {/* Cycle-prevention badge. */}
        {inChain ? (
          <div className="absolute bottom-1 left-1 right-1 flex justify-center">
            <span className="rounded-full border border-amber-400 bg-amber-100/95 px-2 py-0.5 text-[10px] font-medium text-amber-800 shadow-sm">
              ↩ already visiting
            </span>
          </div>
        ) : null}
      </div>

      <Handle type="source" position={Position.Right} />
    </div>
  );
}
