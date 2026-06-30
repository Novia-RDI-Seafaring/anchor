/**
 * LeftToolRail — slim draw.io / Figma style icon column docked to the left
 * edge of the canvas. Replaces the previous floating top toolbar.
 *
 * Layout (top → bottom):
 *   - Shapes   · Rectangle / Circle / Diamond / Container (dashed)
 *   - Cards    · Fact / Note
 *   - Add (+)  · producer upload menu — PDF / CAD / FMU / SysML
 *
 * Ingested files now live in the left files explorer (SourceCluster); the
 * old Library drawer + its `]` shortcut are retired (#220). The `[` shortcut
 * toggles the source cluster (explorer + viewer) so it can yield full width.
 *
 * Two complementary gestures per shape/card icon:
 *
 *   1. Click → arm the tool. The canvas treats the next click (or
 *      click-and-drag) as a placement gesture. Visible state: the icon
 *      gets a subtle highlight; a tiny hint strip pinned at the top of
 *      the canvas reminds the user how to place / cancel. The arming is
 *      held in `uiStore.armedTool`. Click again or press Esc to disarm.
 *
 *   2. HTML5 drag → drop on the canvas. The old gesture is preserved for
 *      power users; the canvas's `onDrop` understands the same payload.
 *
 * Producers (Document / CAD model / FMU / SysML model) don't arm — they
 * need real content. The `+` button opens a popover; picking a type
 * opens a file-input Dialog that POSTs to the matching ingest endpoint.
 * On success the left files explorer (SourceCluster) is expanded so the new
 * artefact is visible.
 */
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cad } from "@/api/cad";
import { canvases } from "@/api/canvases";
import { fmu } from "@/api/fmu";
import { canDragFromToolbar, paletteEntries, type PaletteMeta } from "@/canvas/registry";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/uiStore";

type Props = { workspaceSlug: string };

type ProducerKind = "pdf" | "cad" | "fmu" | "sysml";

const PRODUCER_LABEL: Record<ProducerKind, string> = {
  pdf: "PDF datasheet",
  cad: "CAD model",
  fmu: "FMU model",
  sysml: "SysML model",
};

const PRODUCER_ACCEPT: Record<ProducerKind, string> = {
  pdf: ".pdf",
  cad: ".stl,.step,.stp,.obj,.gltf,.glb,.3mf",
  fmu: ".fmu",
  sysml: ".sysml,.kerml,.txt",
};

export function LeftToolRail({ workspaceSlug }: Props) {
  const toggleSourceCluster = useUiStore((s) => s.toggleSourceCluster);
  const setSourceClusterCollapsed = useUiStore((s) => s.setSourceClusterCollapsed);
  const armedTool = useUiStore((s) => s.armedTool);
  const armTool = useUiStore((s) => s.armTool);
  const disarmTool = useUiStore((s) => s.disarmTool);
  const setSelectedNodeId = useUiStore((s) => s.setSelectedNodeId);
  const setPropertiesOpen = useUiStore((s) => s.setPropertiesOpen);

  const [producerOpen, setProducerOpen] = useState(false);
  const [activeProducer, setActiveProducer] = useState<ProducerKind | null>(null);

  // Keyboard shortcuts:
  //   `[` toggles the source cluster (files explorer + viewer) so the canvas
  //       can go full width. (The old `]` Library-drawer shortcut is gone.)
  //   `Esc` disarms whatever tool is armed.
  // Ignore both when the user is typing into an input/textarea — rename
  // fields use the same keys.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if (event.key === "[" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        if (typing) return;
        event.preventDefault();
        toggleSourceCluster();
      } else if (event.key === "Escape") {
        // Disarming on Esc is the most "draw.io expected" behaviour. Don't
        // preventDefault — other components may also want a chance at Esc.
        // Also deselect the active node so the selection ring + in-flight
        // edits clear. The hook's `canEdit` flip drives the commit.
        if (typing) return; // typing inside an input — let the input own Esc
        if (armedTool) disarmTool();
        setSelectedNodeId(null);
        setPropertiesOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSourceCluster, armedTool, disarmTool, setSelectedNodeId, setPropertiesOpen]);

  const shapes = paletteEntries("shapes");
  const cards = paletteEntries("cards");
  // Sub-canvas is rendered as a dedicated rail tile (not via the `+` upload
  // menu — there's nothing to upload, the child workspace is created server-
  // side on drop). We pull just that one producer entry by name; the rest of
  // the producers (document, cad:model, ...) still live behind the `+`
  // popover because they need a file upload first.
  const subCanvasEntry = paletteEntries("producers").find((e) => e.name === "canvas");
  const specEntry = paletteEntries("producers").find((e) => e.name === "spec");

  const dropPayload = (name: string, meta: PaletteMeta) => {
    const label = meta.noDefaultLabel ? "" : meta.label;
    return {
      node_type: name,
      label,
      ...(meta.width !== undefined ? { width: meta.width } : {}),
      ...(meta.height !== undefined ? { height: meta.height } : {}),
      // For the sub-canvas tile we mark the payload as
      // "create-sub-canvas-on-drop" — CanvasGraph's drop handler will
      // generate a fresh slug, call createSubCanvas, and skip the default
      // addNode call.
      data: {
        ...(meta.data ?? {}),
        ...(name === "canvas" ? { __create_sub_canvas: true } : {}),
      },
    };
  };

  const handleProducerPick = (kind: ProducerKind) => {
    setProducerOpen(false);
    setActiveProducer(kind);
  };

  return (
    <TooltipProvider delayDuration={250}>
      <div
        // Vertical rail along the left edge. Sits at ~52px wide; floats on
        // top of the canvas (the canvas itself fills the full viewport).
        // Background is white with a subtle shadow so it reads as a card.
        className="pointer-events-auto absolute left-3 top-3 z-20 flex w-[44px] flex-col items-center gap-1 rounded-xl border border-neutral-200 bg-white/95 px-1 py-2 shadow-md backdrop-blur"
        role="toolbar"
        aria-orientation="vertical"
        aria-label="Canvas tools"
      >
        <RailGroup label="Shapes">
          {shapes.map((e) => (
            <RailTile
              key={e.name}
              name={e.name}
              meta={e.meta}
              armed={armedTool === e.name}
              onClick={() => armTool(e.name)}
              dropPayload={dropPayload}
            />
          ))}
        </RailGroup>

        <RailDivider />

        <RailGroup label="Cards">
          {cards.map((e) => (
            <RailTile
              key={e.name}
              name={e.name}
              meta={e.meta}
              armed={armedTool === e.name}
              onClick={() => armTool(e.name)}
              dropPayload={dropPayload}
            />
          ))}
        </RailGroup>

        {subCanvasEntry || specEntry ? (
          <>
            <RailDivider />
            <RailGroup label="Producers">
              {specEntry ? (
                <RailTile
                  name={specEntry.name}
                  meta={specEntry.meta}
                  armed={armedTool === specEntry.name}
                  onClick={() => armTool(specEntry.name)}
                  dropPayload={dropPayload}
                />
              ) : null}
              {subCanvasEntry ? (
                <RailTile
                  name={subCanvasEntry.name}
                  meta={subCanvasEntry.meta}
                  armed={armedTool === subCanvasEntry.name}
                  onClick={() => armTool(subCanvasEntry.name)}
                  dropPayload={dropPayload}
                />
              ) : null}
            </RailGroup>
          </>
        ) : null}

        <RailDivider />

        <PopoverPrimitive.Root open={producerOpen} onOpenChange={setProducerOpen}>
          <Tooltip>
            <TooltipTrigger asChild>
              <PopoverPrimitive.Trigger asChild>
                <button
                  type="button"
                  aria-label="Add from producer"
                  className="flex h-9 w-9 items-center justify-center rounded-md text-neutral-700 transition hover:bg-neutral-100 active:bg-neutral-200"
                >
                  <Plus className="size-4" />
                </button>
              </PopoverPrimitive.Trigger>
            </TooltipTrigger>
            <TooltipContent side="right">Add from producer</TooltipContent>
          </Tooltip>
          <PopoverPrimitive.Portal>
            <PopoverPrimitive.Content
              side="right"
              sideOffset={8}
              align="start"
              className="z-50 w-44 rounded-md border border-neutral-200 bg-white p-1 shadow-md"
            >
              {(Object.keys(PRODUCER_LABEL) as ProducerKind[]).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  className="block w-full rounded px-2 py-1.5 text-left text-xs text-neutral-700 hover:bg-neutral-100"
                  onClick={() => handleProducerPick(kind)}
                >
                  {PRODUCER_LABEL[kind]}
                </button>
              ))}
            </PopoverPrimitive.Content>
          </PopoverPrimitive.Portal>
        </PopoverPrimitive.Root>
      </div>

      {/* Top-of-canvas hint strip when a tool is armed. */}
      {armedTool ? (
        <div className="pointer-events-none absolute inset-x-0 top-3 z-20 flex justify-center">
          <div className="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-white/95 px-3 py-1 text-[11px] text-neutral-600 shadow-sm backdrop-blur">
            <span className="font-medium text-neutral-800">{labelFor(armedTool)}</span>
            <span>· Click to place, drag to size · </span>
            <kbd className="rounded border border-neutral-300 bg-neutral-50 px-1 font-mono text-[10px]">Esc</kbd>
            <span>to cancel</span>
          </div>
        </div>
      ) : null}

      {/* Producer upload dialog (lazy — only mounted when a kind is active). */}
      {activeProducer ? (
        <ProducerUploadDialog
          kind={activeProducer}
          workspaceSlug={workspaceSlug}
          onClose={() => {
            setActiveProducer(null);
            // The left files explorer is where a successful upload shows up —
            // make sure the source cluster is expanded so the user sees the
            // new doc / CAD / FMU appear in the list.
            setSourceClusterCollapsed(false);
          }}
        />
      ) : null}
    </TooltipProvider>
  );
}

function labelFor(nodeType: string): string {
  const all = [
    ...paletteEntries("shapes"),
    ...paletteEntries("cards"),
    ...paletteEntries("producers"),
  ];
  return all.find((e) => e.name === nodeType)?.meta.label ?? nodeType;
}

function RailDivider() {
  return <div className="my-0.5 h-px w-6 bg-neutral-200" aria-hidden />;
}

function RailGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1" role="group" aria-label={label}>
      {children}
    </div>
  );
}

function RailTile({
  name,
  meta,
  armed,
  onClick,
  dropPayload,
}: {
  name: string;
  meta: PaletteMeta;
  armed: boolean;
  onClick: () => void;
  dropPayload: (name: string, meta: PaletteMeta) => Record<string, unknown>;
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
          aria-pressed={armed}
          className={cn(
            "flex h-9 w-9 items-center justify-center rounded-md text-neutral-700 transition hover:bg-neutral-100",
            armed && "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
            draggable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer",
          )}
        >
          <Glyph glyph={meta.glyph} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="right">
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
      // Polygon (not a rotated rect) so the icon matches the FunnelNode's
      // clipped silhouette — the rail and the dropped shape share one
      // visual identity.
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
    case "sub-canvas":
      // Two stacked-card icon with a small arrow: signals "link into another
      // canvas". Mirrors the SubCanvasPrimitive's right-pointing chevron.
      return (
        <svg viewBox="0 0 24 24" className={cls} fill="none" strokeWidth={1.5}>
          <rect x="3" y="7" width="12" height="10" rx="1.5" />
          <rect x="9" y="3" width="12" height="10" rx="1.5" />
          <path d="M16 17l2-2-2-2" />
        </svg>
      );
  }
}

/**
 * Producer upload Dialog. File picker pre-filtered to the right extensions.
 * SysML has no upload endpoint yet — show a "coming soon" message so the
 * user knows where the feature will land.
 */
function ProducerUploadDialog({
  kind,
  workspaceSlug,
  onClose,
}: {
  kind: ProducerKind;
  workspaceSlug: string;
  onClose: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("pick a file first");
      return;
    }
    setPending(true);
    setError(null);
    try {
      if (kind === "pdf") {
        // Drop the new doc near the canvas origin; the SSE pipeline will
        // reposition / re-render as the ingest progresses.
        await canvases.uploadFile(workspaceSlug, file, 0, 0);
      } else if (kind === "cad") {
        await cad.upload(file);
      } else if (kind === "fmu") {
        await fmu.upload(file);
      } else {
        // sysml — no upload endpoint yet (anchor_sysml exposes only /render).
        throw new Error("SysML upload not wired yet");
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <DialogPrimitive.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px]" />
        <DialogPrimitive.Content
          className="fixed left-1/2 top-1/2 z-50 w-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-neutral-200 bg-white p-4 shadow-lg"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <DialogPrimitive.Title className="text-sm font-semibold text-neutral-900">
                Upload {PRODUCER_LABEL[kind]}
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="mt-1 text-xs text-neutral-500">
                {kind === "sysml"
                  ? "SysML upload is coming soon — for now use the MCP render tool."
                  : `Pick a file (${PRODUCER_ACCEPT[kind]}) and submit to ingest.`}
              </DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close
              className="rounded p-1 text-neutral-500 hover:bg-neutral-100"
              aria-label="Close"
            >
              <X className="size-4" />
            </DialogPrimitive.Close>
          </div>

          {kind === "sysml" ? (
            <div className="mt-4 rounded border border-dashed border-neutral-300 px-3 py-4 text-xs italic text-neutral-500">
              Use <code className="font-mono">sysml_render</code> via MCP, or
              the <code className="font-mono">/api/sysml/render</code> HTTP
              route, to materialise SysML on this canvas. A direct upload
              endpoint hasn't shipped yet.
            </div>
          ) : (
            <form className="mt-3 flex flex-col gap-3" onSubmit={handleSubmit}>
              <input
                ref={fileRef}
                type="file"
                accept={PRODUCER_ACCEPT[kind]}
                className="text-xs file:mr-3 file:rounded file:border file:border-neutral-300 file:bg-white file:px-2 file:py-1 file:text-xs file:font-medium hover:file:bg-neutral-50"
              />
              {error ? (
                <div className="rounded border border-red-200 bg-red-50 px-2 py-1 text-[11px] text-red-700">
                  {error}
                </div>
              ) : null}
              <div className="flex justify-end gap-2">
                <DialogPrimitive.Close
                  className="rounded border border-neutral-300 px-3 py-1 text-xs text-neutral-700 hover:bg-neutral-50"
                  type="button"
                >
                  Cancel
                </DialogPrimitive.Close>
                <button
                  type="submit"
                  disabled={pending}
                  className="rounded bg-neutral-900 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
                >
                  {pending ? "uploading…" : "Upload"}
                </button>
              </div>
            </form>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
