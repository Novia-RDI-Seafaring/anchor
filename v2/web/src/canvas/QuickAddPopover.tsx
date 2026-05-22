/**
 * QuickAddPopover — Miro-style "Add the same object" picker.
 *
 * Appears at the release point of a `DirectionalConnectors` drag onto
 * empty pane. Offers a 3×3 grid of shape glyphs with the source node's
 * type pre-highlighted (sky-blue ring) so the obvious Enter-key path is
 * "add the same kind of thing". The picker also exposes an "All shapes"
 * link that defers to the full palette via the LeftToolRail's arming
 * flow — out of scope for this PR, treated as a soft fallback.
 *
 * Keyboard map:
 *   - Enter   → create the highlighted (source-type) node + edge.
 *   - Escape  → dismiss without creating anything.
 *   - Tab     → walks the grid via native focus traversal.
 *
 * Coordination:
 *   - Creates the node via `canvases.addNode`, then immediately wires a
 *     `floating` edge from the source to the new node. SSE delivers the
 *     canonical patches; the canvas re-renders.
 *   - On creation, stamps the new id in `useUiStore.requestInlineRename`
 *     so the shape primitive's rename input gets focused. Matches the
 *     LeftToolRail's arm-and-place experience.
 *
 *   - The grid sources its entries from `paletteEntries('shapes')` and
 *     `paletteEntries('cards')`. The registry is the single source of
 *     truth — when a new shape ships its tile, the popover picks it up
 *     for free.
 */
import { useEffect, useMemo, useRef } from "react";

import { canvases } from "@/api/canvases";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/uiStore";

import { paletteEntries, type PaletteMeta } from "./registry";

type Props = {
  workspaceSlug: string;
  /** Screen-space anchor (the pointer-up location). */
  screenAnchor: { x: number; y: number };
  /** Flow-space drop point for the new node. */
  flowDrop: { x: number; y: number };
  /** Source node id — the edge will land on this. */
  sourceId: string;
  /** Source node type — highlighted in the grid; default for Enter. */
  sourceType: string;
  onClose: () => void;
};

export function QuickAddPopover({
  workspaceSlug,
  screenAnchor,
  flowDrop,
  sourceId,
  sourceType,
  onClose,
}: Props) {
  // Pull shapes + cards from the registry so the popover stays in sync
  // with the LeftToolRail. The full "All shapes" link reveals the rest.
  const entries = useMemo(() => {
    const items = [...paletteEntries("shapes"), ...paletteEntries("cards")];
    // Cap the grid at 9 (3×3); anything else lands behind "All shapes".
    return items.slice(0, 9);
  }, []);

  const popoverRef = useRef<HTMLDivElement | null>(null);

  const createWithType = async (nodeType: string) => {
    try {
      const all = [...paletteEntries("shapes"), ...paletteEntries("cards")];
      const meta = all.find((e) => e.name === nodeType)?.meta;
      const label = meta?.noDefaultLabel ? "" : meta?.label ?? "";
      const width = meta?.width;
      const height = meta?.height;
      const res = (await canvases.addNode(workspaceSlug, {
        node_type: nodeType,
        label,
        x: flowDrop.x,
        y: flowDrop.y,
        ...(width !== undefined ? { width } : {}),
        ...(height !== undefined ? { height } : {}),
        data: {
          ...(meta?.data ?? {}),
          ...(width !== undefined ? { width } : {}),
          ...(height !== undefined ? { height } : {}),
        },
      })) as { event?: { payload?: { id?: string } } } | null;
      const newId = res?.event?.payload?.id;
      if (newId) {
        await canvases.addEdge(workspaceSlug, {
          source: sourceId,
          target: newId,
          edge_type: "floating",
          data: {},
        });
        useUiStore.getState().setSelectedNodeId(newId);
        useUiStore.getState().requestInlineRename(newId);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("quick-add creation failed", err);
    } finally {
      onClose();
    }
  };

  // Keyboard map. Bound to the window so the user doesn't have to focus
  // the popover root before Enter / Escape land.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "Enter") {
        event.preventDefault();
        // Enter creates the "same object" — the source's type. Fall back
        // to the first grid entry if the source type isn't drag-creatable
        // (a producer like `document` couldn't be cloned without content).
        const fallback = entries[0]?.name ?? "concept";
        const draftable = entries.some((e) => e.name === sourceType);
        void createWithType(draftable ? sourceType : fallback);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entries, sourceType]);

  // Click-outside dismissal. Mousedown is the right trigger — by the
  // time the click fires the picker would already be gone.
  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (!popoverRef.current) return;
      if (target && popoverRef.current.contains(target)) return;
      onClose();
    };
    window.addEventListener("pointerdown", onPointer);
    return () => window.removeEventListener("pointerdown", onPointer);
  }, [onClose]);

  // Position: nudge the popover so it doesn't overflow the right / bottom
  // edges. 240×220 covers the grid + label + footer.
  const W = 240;
  const H = 220;
  const left = Math.min(window.innerWidth - W - 8, Math.max(8, screenAnchor.x + 8));
  const top = Math.min(window.innerHeight - H - 8, Math.max(8, screenAnchor.y + 8));

  return (
    <div
      ref={popoverRef}
      data-testid="quick-add-popover"
      style={{
        position: "fixed",
        left,
        top,
        width: W,
        zIndex: 40,
      }}
      onPointerDown={(e) => e.stopPropagation()}
      className="rounded-lg border border-neutral-200 bg-white p-2 shadow-lg"
    >
      {/* Same-type primary action — a full-width button at the top so
          the obvious "make another of the same" path is one click, not
          a hunt through the grid. The button shows the source's
          friendly label so the user sees what they're about to make.
          Enter has the same effect. */}
      {(() => {
        const same = entries.find((e) => e.name === sourceType);
        const label = same?.meta.label ?? sourceType;
        return (
          <button
            type="button"
            onClick={() => void createWithType(same?.name ?? sourceType)}
            className="mb-2 flex w-full items-center justify-between gap-2 rounded-md border border-sky-300 bg-sky-50 px-2 py-1.5 text-left text-[12px] font-medium text-sky-900 transition hover:bg-sky-100"
          >
            <span className="flex items-center gap-2">
              {same?.meta.glyph ? <TileGlyph glyph={same.meta.glyph} /> : null}
              <span>Add another {label.toLowerCase()}</span>
            </span>
            <kbd className="rounded border border-sky-300 bg-white px-1 font-mono text-[10px] text-sky-700">⏎</kbd>
          </button>
        );
      })()}
      <div className="mb-1 px-1 text-[10px] uppercase tracking-wide text-neutral-500">
        or pick a different shape
      </div>
      <div className="grid grid-cols-3 gap-1">
        {entries.map((e) => (
          <ShapeTile
            key={e.name}
            name={e.name}
            meta={e.meta}
            highlighted={e.name === sourceType}
            onPick={() => void createWithType(e.name)}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={() => {
          // "All shapes" — for now we just dismiss the popover so the
          // user can grab the full palette from the LeftToolRail. A
          // proper expanded grid is a follow-up. We document this on
          // the rail's `armTool` action so the path is discoverable.
          onClose();
        }}
        className="mt-2 w-full rounded px-2 py-1 text-left text-[11px] text-neutral-500 hover:bg-neutral-50"
      >
        All shapes…
      </button>
    </div>
  );
}

function ShapeTile({
  name,
  meta,
  highlighted,
  onPick,
}: {
  name: string;
  meta: PaletteMeta;
  highlighted: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      title={meta.label}
      aria-label={meta.label}
      onClick={onPick}
      data-testid={`quick-add-tile-${name}`}
      className={cn(
        "flex h-14 w-full items-center justify-center rounded-md border text-neutral-700 transition hover:bg-neutral-50",
        highlighted
          ? "border-sky-400 ring-2 ring-sky-200"
          : "border-neutral-200",
      )}
    >
      <TileGlyph glyph={meta.glyph} />
    </button>
  );
}

function TileGlyph({ glyph }: { glyph: PaletteMeta["glyph"] }) {
  const cls = "size-5 stroke-current";
  // Lightweight inline SVG — keeps the popover self-contained instead of
  // re-importing LeftToolRail's <Glyph>. Same shape vocabulary so the
  // tile reads as "the same thing" as the rail's tile.
  switch (glyph) {
    case "rect":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="3" y="6" width="18" height="12" rx="2" />
        </svg>
      );
    case "circle":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
    case "diamond":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <polygon points="12,3 21,12 12,21 3,12" />
        </svg>
      );
    case "dashed-rect":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5} strokeDasharray="3 2">
          <rect x="3" y="5" width="18" height="14" rx="2" />
        </svg>
      );
    case "note":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <path d="M5 5h14v10l-4 4H5z" />
          <path d="M15 19v-4h4" />
        </svg>
      );
    case "fact":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="4" y="6" width="16" height="12" rx="2" />
          <path d="M7 10h10M7 13h7" />
        </svg>
      );
    default:
      // Anything else (producer glyphs landing inside the cap) gets a
      // generic "?" tile. Producers are filtered out by paletteEntries
      // group call, so this branch is mostly a typesafety guard.
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <circle cx="12" cy="12" r="8" />
          <path d="M9 10a3 3 0 1 1 4 2.5 2 2 0 0 0-1 1.5M12 17h0" />
        </svg>
      );
  }
}
