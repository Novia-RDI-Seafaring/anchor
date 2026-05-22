/**
 * CanvasesPanel — peer of `Library.tsx` inside the LibraryDrawer.
 *
 * Lists every workspace returned by `canvases.list()` so the user can drag
 * an *existing* canvas onto the current canvas and have it become a linked
 * sub-canvas tile. The drag emits an `application/x-anchor-canvas-link`
 * payload; `CanvasGraph`'s drop handler turns it into a `canvas` node with
 * `data.canvas_slug` pointing at the dragged workspace — no new child
 * workspace is created (that's what the rail's `+ Sub-canvas` button does).
 *
 * Filtering rules:
 *   - Exclude the current canvas (no self-link).
 *   - Exclude canvases already in the current canvas's outgoing
 *     `references` (no duplicate link). We read references from the
 *     envelope when present; otherwise the current canvas wouldn't appear
 *     in the list anyway, so we just skip the dedupe.
 */
import { useEffect, useState } from "react";

import {
  canvases,
  type WorkspaceListEntry,
} from "@/api/canvases";

type Props = { workspaceSlug: string };

export const CANVAS_LINK_MIME = "application/x-anchor-canvas-link";

export type CanvasLinkPayload = {
  slug: string;
  title: string;
};

export function CanvasesPanel({ workspaceSlug }: Props) {
  const [items, setItems] = useState<WorkspaceListEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const list = await canvases.list();
        if (!cancelled) setItems(list);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    };

    refresh();
    // Light polling — same cadence as the Documents panel.
    const id = window.setInterval(refresh, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const visible = filterAttachable(items, workspaceSlug);

  return (
    <div className="space-y-3">
      <Section
        title={`Canvases (${visible.length})`}
        subtitle="drag to link"
      >
        {visible.length === 0 ? (
          <Empty hint="no other canvases to link — create one from the canvases list" />
        ) : (
          visible.map((c) => (
            <DraggableCanvasItem
              key={c.slug}
              entry={c}
            />
          ))
        )}
      </Section>

      {error ? (
        <div className="px-2 text-[10px] text-red-600">error: {error}</div>
      ) : null}
    </div>
  );
}

/**
 * Pure filter — exported for test. Drops the current canvas plus any
 * canvas already in the current canvas's outgoing `references`.
 */
export function filterAttachable(
  items: WorkspaceListEntry[],
  currentSlug: string,
): WorkspaceListEntry[] {
  const current = items.find((it) => it.slug === currentSlug);
  const alreadyLinked = new Set<string>(current?.references ?? []);
  return items.filter(
    (it) => it.slug !== currentSlug && !alreadyLinked.has(it.slug),
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between px-2 pt-1 pb-1">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          {title}
        </div>
        {subtitle ? (
          <div className="text-[9px] italic text-neutral-400">{subtitle}</div>
        ) : null}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Empty({ hint }: { hint: string }) {
  return (
    <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
      {hint}
    </div>
  );
}

function DraggableCanvasItem({ entry }: { entry: WorkspaceListEntry }) {
  const title = entry.title || entry.slug;
  // Stats line is opt-in: the envelope may omit counts (e.g. older
  // backend) — fall back to a slug-only subtitle.
  const hasCounts =
    typeof entry.node_count === "number" && typeof entry.edge_count === "number";
  const stats = hasCounts
    ? `${entry.node_count} nodes · ${entry.edge_count} edges`
    : entry.slug;

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "link";
        const payload: CanvasLinkPayload = { slug: entry.slug, title };
        e.dataTransfer.setData(CANVAS_LINK_MIME, JSON.stringify(payload));
      }}
      className="cursor-grab rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs hover:bg-neutral-50 active:cursor-grabbing"
      title={`Link existing canvas (${entry.slug})`}
    >
      <div className="flex items-center gap-1.5 truncate font-medium text-neutral-800">
        <CanvasGlyph />
        <span className="truncate">{title}</span>
        {entry.title ? (
          <span className="truncate text-[10px] font-normal text-neutral-400">
            ({entry.slug})
          </span>
        ) : null}
      </div>
      <div className="text-[10px] italic text-neutral-500">{stats}</div>
    </div>
  );
}

function CanvasGlyph() {
  // Hexagon-ish "linked canvas" indicator. Matches the sub-canvas tile's
  // visual identity in spirit without pulling in the heavier primitive.
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      className="shrink-0 text-neutral-500"
      aria-hidden="true"
    >
      <polygon points="6,1 11,3.5 11,8.5 6,11 1,8.5 1,3.5" />
    </svg>
  );
}
