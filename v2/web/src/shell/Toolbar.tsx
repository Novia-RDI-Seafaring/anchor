/**
 * Toolbar — floating top-of-canvas pill that replaces the old LeftRail.
 *
 * Layout: a single horizontal row of small icon buttons grouped into three
 * sections (Shapes, Cards, Producers), separated by thin vertical dividers,
 * with a final "Library" button on the right that opens the right-side
 * drawer (also bound to `]`). Sits just under the page header, centred.
 *
 * Drag-out: every shape/card carries the same `application/x-anchor-node`
 * payload the old palette emitted, so the canvas's drop handler is
 * unchanged. Click-to-add drops at the current visible-flow centre as a
 * sensible default.
 *
 * Producers are *informational* in the toolbar — Document, CAD, SysML &c.
 * always need real content (a document slug, a SysML model, ...) so the
 * toolbar advertises them with a tooltip and routes clicks to the Library
 * drawer. The registry is the source of truth: see canvas/registry.ts
 * `paletteEntries('producers')`.
 *
 * Future-proofing note: a centred floating chat input may land at the
 * bottom-middle of the canvas later. This toolbar pins itself to the top,
 * the Library drawer slides in from the right, and ActivityToast sits in
 * the bottom-right (see CanvasShell) — none of those will fight a future
 * bottom-centre input. Keep new floating UI off the centre axis.
 */
import { useReactFlow } from "@xyflow/react";
import { Library as LibraryIcon } from "lucide-react";
import { useEffect } from "react";

import { canvases } from "@/api/canvases";
import { canDragFromToolbar, paletteEntries, type PaletteMeta } from "@/canvas/registry";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useUiStore } from "@/stores/uiStore";

type Props = { workspaceSlug: string };

export function Toolbar({ workspaceSlug }: Props) {
  const { screenToFlowPosition } = useReactFlow();
  const setLibraryDrawerOpen = useUiStore((s) => s.setLibraryDrawerOpen);
  const toggleLibraryDrawer = useUiStore((s) => s.toggleLibraryDrawer);
  const libraryDrawerOpen = useUiStore((s) => s.libraryDrawerOpen);

  // `]` toggles the Library drawer. Ignore when typing in inputs (rename
  // fields use the same letters).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "]") return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      toggleLibraryDrawer();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleLibraryDrawer]);

  const shapes = paletteEntries("shapes");
  const cards = paletteEntries("cards");
  const producers = paletteEntries("producers");

  const dropPayload = (name: string, meta: PaletteMeta) => {
    const label = meta.noDefaultLabel ? "" : meta.label;
    return {
      node_type: name,
      label,
      ...(meta.width !== undefined ? { width: meta.width } : {}),
      ...(meta.height !== undefined ? { height: meta.height } : {}),
      data: meta.data ?? {},
    };
  };

  const handleClick = async (name: string, meta: PaletteMeta) => {
    // Producers route to the Library drawer — they need real content.
    if (!canDragFromToolbar(name)) {
      setLibraryDrawerOpen(true);
      return;
    }
    const center = screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    });
    const spec = dropPayload(name, meta);
    try {
      await canvases.addNode(workspaceSlug, {
        ...spec,
        x: center.x,
        y: center.y,
      });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("toolbar addNode failed", err);
    }
  };

  return (
    <TooltipProvider delayDuration={250}>
      <div
        // Top-centred floating pill. `pointer-events-auto` so clicks land
        // even though the parent overlay is `pointer-events-none`. Padding
        // mirrors a Mac dock — comfortable target size without dominating.
        className="pointer-events-auto inline-flex items-center gap-1 rounded-xl border border-neutral-200 bg-white/95 px-1.5 py-1 shadow-md backdrop-blur"
        role="toolbar"
        aria-label="Canvas tools"
      >
        <Group label="Shapes">
          {shapes.map((e) => (
            <ToolbarTile
              key={e.name}
              name={e.name}
              meta={e.meta}
              workspaceSlug={workspaceSlug}
              onClick={() => handleClick(e.name, e.meta)}
              dropPayload={dropPayload}
            />
          ))}
        </Group>

        <Divider />

        <Group label="Cards">
          {cards.map((e) => (
            <ToolbarTile
              key={e.name}
              name={e.name}
              meta={e.meta}
              workspaceSlug={workspaceSlug}
              onClick={() => handleClick(e.name, e.meta)}
              dropPayload={dropPayload}
            />
          ))}
        </Group>

        <Divider />

        <Group label="Producers">
          {producers.map((e) => (
            <ToolbarTile
              key={e.name}
              name={e.name}
              meta={e.meta}
              workspaceSlug={workspaceSlug}
              onClick={() => handleClick(e.name, e.meta)}
              dropPayload={dropPayload}
              producer
            />
          ))}
        </Group>

        <Divider />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={toggleLibraryDrawer}
              aria-label="Library"
              aria-pressed={libraryDrawerOpen}
              className={libraryDrawerOpen ? "bg-neutral-200 text-neutral-900" : ""}
            >
              <LibraryIcon className="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Library · <kbd className="font-mono">]</kbd>
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}

function Divider() {
  return <div className="mx-0.5 h-5 w-px self-center bg-neutral-200" aria-hidden />;
}

function Group({ label: _label, children }: { label: string; children: React.ReactNode }) {
  // `label` exists for screen-readers via aria, but we don't render a
  // visible heading — the toolbar is icon-first by design.
  return (
    <div className="flex items-center gap-0.5" role="group" aria-label={_label}>
      {children}
    </div>
  );
}

function ToolbarTile({
  name,
  meta,
  onClick,
  dropPayload,
  producer = false,
}: {
  name: string;
  meta: PaletteMeta;
  workspaceSlug: string;
  onClick: () => void;
  dropPayload: (name: string, meta: PaletteMeta) => Record<string, unknown>;
  producer?: boolean;
}) {
  const draggable = canDragFromToolbar(name);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          draggable={draggable}
          onDragStart={
            draggable
              ? (event) => {
                  event.dataTransfer.effectAllowed = "copy";
                  event.dataTransfer.setData(
                    "application/x-anchor-node",
                    JSON.stringify(dropPayload(name, meta)),
                  );
                }
              : undefined
          }
          onClick={onClick}
          aria-label={meta.label}
          className={`flex h-7 w-7 items-center justify-center rounded-md text-neutral-700 transition hover:bg-neutral-100 active:bg-neutral-200 ${
            producer ? "text-neutral-500 hover:text-neutral-800" : ""
          } ${draggable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"}`}
        >
          <Glyph glyph={meta.glyph} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <div className="font-medium">{meta.label}</div>
        {meta.hint ? (
          <div className="text-[10px] text-neutral-500">{meta.hint}</div>
        ) : null}
      </TooltipContent>
    </Tooltip>
  );
}

function Glyph({ glyph }: { glyph: PaletteMeta["glyph"] }) {
  const cls = "size-4 stroke-current";
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
          <rect x="6" y="6" width="12" height="12" rx="1" transform="rotate(45 12 12)" />
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
    case "page":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <path d="M6 3h8l4 4v14H6z" />
          <path d="M14 3v4h4" />
          <path d="M9 12h6M9 15h6M9 18h4" />
        </svg>
      );
    case "table":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="3" y="5" width="18" height="14" rx="1" />
          <path d="M3 10h18M3 15h18M9 5v14" />
        </svg>
      );
    case "cube":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" />
          <path d="M4 7.5L12 12l8-4.5" />
          <path d="M12 12v9" />
        </svg>
      );
    case "block":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="4" y="5" width="16" height="14" rx="1" />
          <path d="M4 9h16M9 5v14" />
        </svg>
      );
    case "requirement":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="4" y="5" width="16" height="14" rx="1" />
          <path d="M8 10h8M8 13h6M8 16h4" />
        </svg>
      );
    case "package":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <path d="M4 8h6l1 2h9v9H4z" />
        </svg>
      );
    case "fmu":
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="4" y="6" width="16" height="12" rx="1" />
          <path d="M4 10h2M4 14h2M18 10h2M18 14h2" />
          <path d="M9 12h6" />
        </svg>
      );
  }
}
