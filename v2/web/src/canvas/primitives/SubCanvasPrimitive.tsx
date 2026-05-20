/**
 * SubCanvasPrimitive — a link from one canvas to another.
 *
 * The user's design for hierarchical systems: a top-level "Plant" canvas
 * holds canvas-nodes for "Pump loop", "Heat exchanger", etc. Each of
 * those is a fully editable child canvas, drilled into by double-clicking
 * the tile.
 *
 * Renderer responsibilities:
 *   - Show a 240x160 tile with the child's title (or slug) + a "→" hint.
 *   - Lazily fetch a PNG snapshot of the child canvas as a live thumbnail.
 *     Snapshots cache in-memory for the session; on remount we refetch so
 *     stale-after-mutation thumbnails self-heal over time. Heavier
 *     invalidation (refetch on `canvas:*` events that touch the child)
 *     is a follow-up.
 *   - Surface a "↩ already visiting" badge when the child slug is already
 *     in the user's breadcrumb chain — cycle prevention, see breadcrumb.ts.
 *     Double-click is disabled in that case.
 *
 * Navigation lives in CanvasGraph.tsx's `onNodeDoubleClick` (see there).
 * This primitive only renders.
 *
 * Inline rename edits `data.title` only — the `canvas_slug` is the link
 * key and must stay stable. The `useInlineField` hook patches the
 * `data.title` field; the SSE echo updates the canonical store.
 */
import { useEffect, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { breadcrumb } from "@/canvas/breadcrumb";
import { useInlineField } from "@/canvas/useInlineField";

type SubCanvasData = {
  canvas_slug?: string;
  title?: string;
  label?: string;
};

/** Process-wide thumbnail cache — keyed by canvas_slug → object URL. */
const THUMB_CACHE = new Map<string, string>();

async function fetchThumb(slug: string): Promise<string | null> {
  const cached = THUMB_CACHE.get(slug);
  if (cached) return cached;
  try {
    const rsp = await fetch(canvases.snapshotUrl(slug), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ format: "png", full_page: true }),
    });
    if (!rsp.ok) return null;
    const blob = await rsp.blob();
    const url = URL.createObjectURL(blob);
    THUMB_CACHE.set(slug, url);
    return url;
  } catch {
    return null;
  }
}

export function SubCanvasPrimitive({ id, data, selected }: NodeProps) {
  const d = (data ?? {}) as SubCanvasData;
  const subSlug = d.canvas_slug ?? "";
  const title = d.title ?? d.label ?? subSlug;
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [thumbState, setThumbState] = useState<"idle" | "loading" | "ready" | "failed">("idle");

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

  useEffect(() => {
    if (!subSlug) return;
    let cancelled = false;
    setThumbState("loading");
    fetchThumb(subSlug).then((url) => {
      if (cancelled) return;
      if (url) {
        setThumbUrl(url);
        setThumbState("ready");
      } else {
        setThumbState("failed");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [subSlug]);

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

      {/* Body — thumbnail or placeholder. */}
      <div className="nodrag nopan relative h-[112px] w-full bg-neutral-100">
        {thumbState === "ready" && thumbUrl ? (
          // Live snapshot of the child canvas. `object-cover` so the tile
          // shows the canvas centre even if the child's full-page snapshot
          // is much wider/taller.
          <img
            src={thumbUrl}
            alt={`snapshot of ${subSlug}`}
            className="block h-full w-full select-none object-cover"
            draggable={false}
            onError={() => setThumbState("failed")}
          />
        ) : thumbState === "loading" ? (
          <div className="flex h-full w-full items-center justify-center text-[11px] italic text-neutral-400">
            loading…
          </div>
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-neutral-400">
            <svg viewBox="0 0 24 24" className="size-6" fill="none" strokeWidth={1.4} stroke="currentColor">
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="M3 9h18" />
              <path d="M9 13l2 2 4-4" />
            </svg>
            <div className="text-[10px]">
              {thumbState === "failed" ? "no snapshot yet" : "empty canvas"}
            </div>
          </div>
        )}

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
