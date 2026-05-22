/**
 * EdgeContextToolbar — Miro-style floating mini-toolbar for the selected
 * edge. Mirrors `NodeContextToolbar` but with edge-specific chips.
 *
 * Positioning: anchored at the selected edge's midpoint in flow space,
 * converted to screen space via `flowToScreenPosition`. Re-anchors on
 * pan/zoom by subscribing to `useStore((s) => s.transform)`.
 *
 * Chips (left → right):
 *   - Start cap (▾)        — data.start_marker ∈ {none, arrow, circle}
 *   - Route                — edge_type ∈ {floating, smooth, step, straight}
 *   - End cap (▾)          — data.end_marker
 *   - Line style           — data.stroke_style ∈ {solid, dashed, dotted}
 *   - Stroke colour swatch — data.stroke_color (eight palette tones)
 *   - Label toggle (T+)    — top-level edge `label`
 *   - Lock                 — data.locked
 *   - More (⋮)             — Delete / Edit data JSON
 *
 * Every change goes through `canvases.patchEdge`, which the backend's
 * HTTP/MCP/CLI parity layer already handles. The user's data is merged
 * client-side before send so unrelated `data.*` fields survive.
 */
import { useReactFlow, useStore } from "@xyflow/react";
import {
  ChevronDown,
  Circle,
  Lock,
  MinusCircle,
  MoreVertical,
  MoveRight,
  Slash,
  Trash2,
  Type,
  Unlock,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { canvases } from "@/api/canvases";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { STROKE_SWATCHES } from "./colors";
import {
  DEFAULT_EDGE_STROKE,
  resolveEdgeUserStyle,
  type EdgeCap,
  type EdgeStrokeStyle,
} from "./edges/edge-style";

type Props = {
  workspaceSlug: string;
};

/**
 * Compute an approximate midpoint of the edge in flow coordinates by
 * averaging the source / target node centres + any waypoints. This is
 * coarse but matches the user's "where the toolbar should sit" intuition
 * for every router (curves through the midpoint of the bounding box of
 * the route).
 */
function edgeMidpointFlow(opts: {
  sourceCentre: { x: number; y: number };
  targetCentre: { x: number; y: number };
  waypoints: Array<{ x: number; y: number }>;
}): { x: number; y: number } {
  const pts = [opts.sourceCentre, ...opts.waypoints, opts.targetCentre];
  let sx = 0, sy = 0;
  for (const p of pts) { sx += p.x; sy += p.y; }
  return { x: sx / pts.length, y: sy / pts.length };
}

function nodeCentre(n: {
  x: number;
  y: number;
  data?: Record<string, unknown>;
} | undefined): { x: number; y: number } | null {
  if (!n) return null;
  const w = (n.data?.width as number | undefined) ?? 100;
  const h = (n.data?.height as number | undefined) ?? 100;
  return { x: n.x + w / 2, y: n.y + h / 2 };
}

export function EdgeContextToolbar({ workspaceSlug }: Props) {
  const transform = useStore((s) => s.transform);
  const { flowToScreenPosition } = useReactFlow();
  const selectedEdgeId = useUiStore((s) => s.selectedEdgeId);
  const setSelectedEdgeId = useUiStore((s) => s.setSelectedEdgeId);
  const edges = useCanvasStore((s) => s.edges);
  const nodes = useCanvasStore((s) => s.nodes);

  const edge = selectedEdgeId ? edges[selectedEdgeId] ?? null : null;

  const screenPos = useMemo(() => {
    if (!edge) return null;
    const src = nodeCentre(nodes[edge.source]);
    const tgt = nodeCentre(nodes[edge.target]);
    if (!src || !tgt) return null;
    const user = resolveEdgeUserStyle(edge.data);
    const mid = edgeMidpointFlow({ sourceCentre: src, targetCentre: tgt, waypoints: user.waypoints });
    return flowToScreenPosition(mid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edge, nodes, transform]);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  useEffect(() => { setConfirmingDelete(false); }, [selectedEdgeId]);

  if (!edge || !screenPos) return null;

  const user = resolveEdgeUserStyle(edge.data);
  const currentColor = (edge.data?.stroke_color as string | undefined) ?? DEFAULT_EDGE_STROKE;
  const routeMode = edge.edge_type;

  const patch = async (fields: Record<string, unknown>) => {
    try {
      await canvases.patchEdge(workspaceSlug, edge.id, fields);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("edge patch failed", err);
    }
  };

  const patchData = (changes: Record<string, unknown>) =>
    patch({ data: { ...(edge.data ?? {}), ...changes } });

  const setRoute = (mode: "floating" | "smooth" | "step" | "straight") =>
    patch({ edge_type: mode });

  const setCap = (which: "start_marker" | "end_marker", value: EdgeCap) =>
    patchData({ [which]: value });

  const setStrokeStyle = (value: EdgeStrokeStyle) => patchData({ stroke_style: value });
  const setStrokeColor = (value: string | undefined) =>
    patchData({ stroke_color: value });

  const toggleLock = () => patchData({ locked: !user.locked });

  const setLabel = (value: string) => patch({ label: value });

  const handleDelete = async () => {
    try {
      await canvases.removeEdge(workspaceSlug, edge.id);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("edge delete failed", err);
    }
    setSelectedEdgeId(null);
    setConfirmingDelete(false);
  };

  const TOOLBAR_OFFSET = 28;
  const style: React.CSSProperties = {
    position: "fixed",
    left: screenPos.x,
    top: Math.max(8, screenPos.y - TOOLBAR_OFFSET),
    transform: "translate(-50%, -100%)",
    zIndex: 30,
  };

  return (
    <div
      data-testid="edge-context-toolbar"
      style={style}
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <div className="flex items-center gap-1 rounded-md border border-neutral-200 bg-white px-1 py-1 shadow-md">
        {/* Start cap */}
        <CapPicker
          label="Start"
          value={user.startMarker}
          onPick={(v) => void setCap("start_marker", v)}
          testId="edge-chip-start"
        />

        {/* Route mode */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Route mode"
              title="Route mode"
              data-testid="edge-chip-route"
            >
              <span className="text-[11px] capitalize">{routeMode || "floating"}</span>
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="center" sideOffset={6}>
            <DropdownMenuLabel>Route</DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => void setRoute("floating")}>Floating</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void setRoute("smooth")}>Smooth</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void setRoute("step")}>Step</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void setRoute("straight")}>Straight</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* End cap */}
        <CapPicker
          label="End"
          value={user.endMarker}
          onPick={(v) => void setCap("end_marker", v)}
          testId="edge-chip-end"
        />

        {/* Line style */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Line style"
              title="Line style"
              data-testid="edge-chip-style"
            >
              <LineStyleIcon style={user.strokeStyle} />
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="center" sideOffset={6}>
            <DropdownMenuItem onSelect={() => void setStrokeStyle("solid")}>Solid</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void setStrokeStyle("dashed")}>Dashed</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void setStrokeStyle("dotted")}>Dotted</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Stroke colour */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              data-testid="edge-chip-color"
              aria-label="Stroke colour"
              title="Stroke colour"
              className="inline-flex h-6 items-center gap-1 rounded border border-neutral-300 bg-white px-1.5 transition hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <span
                className="block h-3.5 w-3.5 rounded-full border border-neutral-400"
                style={{ background: currentColor }}
                aria-hidden
              />
              <ChevronDown className="size-3 text-neutral-500" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="center" sideOffset={6}>
            <div className="flex flex-col gap-2 min-w-[12rem]" data-testid="edge-color-swatches">
              <div className="flex flex-wrap items-center gap-1">
                {STROKE_SWATCHES.map((sw) => (
                  <button
                    key={`edge-color-${sw.label}`}
                    type="button"
                    role="menuitem"
                    aria-label={`edge color ${sw.label}`}
                    title={sw.label}
                    onClick={() => void setStrokeColor(sw.stroke)}
                    className={cn(
                      "h-5 w-5 rounded-full border border-neutral-300 transition hover:scale-110 focus:outline-none focus:ring-2 focus:ring-sky-500",
                    )}
                    style={{ background: sw.stroke }}
                  />
                ))}
              </div>
              <div className="flex items-center gap-2 text-[11px]">
                <button
                  type="button"
                  onClick={() => void setStrokeColor(undefined)}
                  className="rounded px-1.5 py-0.5 text-neutral-600 hover:bg-neutral-100"
                >
                  Reset
                </button>
              </div>
            </div>
          </PopoverContent>
        </Popover>

        {/* Label toggle */}
        <LabelEditor edge={edge} onSet={(v) => void setLabel(v)} />

        {/* Lock */}
        <Button
          variant="ghost"
          size="icon"
          title={user.locked ? "Unlock edge" : "Lock edge"}
          aria-label={user.locked ? "Unlock edge" : "Lock edge"}
          aria-pressed={user.locked}
          onClick={() => void toggleLock()}
          data-testid="edge-chip-lock"
          className={user.locked ? "bg-neutral-100 text-neutral-900" : undefined}
        >
          {user.locked ? <Lock className="size-3.5" /> : <Unlock className="size-3.5" />}
        </Button>

        {/* Delete — two-tap inline confirm. */}
        {confirmingDelete ? (
          <Button
            variant="outline"
            size="sm"
            title="Click again to confirm"
            aria-label="Confirm delete"
            className="border-red-300 text-red-700 hover:bg-red-50"
            onClick={() => void handleDelete()}
          >
            <Trash2 className="size-3.5" />
            <span className="text-[11px]">Delete?</span>
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="icon"
            title="Delete edge"
            aria-label="Delete edge"
            onClick={() => setConfirmingDelete(true)}
          >
            <Trash2 className="size-3.5" />
          </Button>
        )}

        {/* More */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              title="More actions"
              aria-label="More edge actions"
            >
              <MoreVertical className="size-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" sideOffset={6}>
            <DropdownMenuLabel>Edge</DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => void handleDelete()}>Delete</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                const current = JSON.stringify(edge.data ?? {}, null, 2);
                const next = window.prompt("Edit edge data (JSON):", current);
                if (next == null) return;
                try {
                  const parsed = JSON.parse(next);
                  if (parsed && typeof parsed === "object") void patch({ data: parsed });
                } catch {
                  window.alert("Invalid JSON; edit cancelled.");
                }
              }}
            >
              Edit data…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

/** Per-end cap picker — small ▾ dropdown of {None, Arrow, Circle}. */
function CapPicker({
  label, value, onPick, testId,
}: {
  label: string;
  value: EdgeCap;
  onPick: (v: EdgeCap) => void;
  testId: string;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`${label} cap`}
          title={`${label} cap`}
          data-testid={testId}
        >
          <CapGlyph cap={value} />
          <span className="text-[11px]">{label}</span>
          <ChevronDown className="size-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="center" sideOffset={6}>
        <DropdownMenuItem onSelect={() => onPick("none")}>
          <MinusCircle className="mr-1.5 size-3" /> None
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onPick("arrow")}>
          <MoveRight className="mr-1.5 size-3" /> Arrow
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => onPick("circle")}>
          <Circle className="mr-1.5 size-3" /> Circle
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function CapGlyph({ cap }: { cap: EdgeCap }) {
  if (cap === "arrow") return <MoveRight className="size-3.5" />;
  if (cap === "circle") return <Circle className="size-3.5" />;
  return <MinusCircle className="size-3.5" />;
}

function LineStyleIcon({ style }: { style: EdgeStrokeStyle }) {
  // Tiny inline SVG mock of the line style.
  const dash =
    style === "solid" ? undefined : style === "dashed" ? "4 2" : "1 2";
  return (
    <svg width="22" height="10" viewBox="0 0 22 10" aria-hidden>
      <line
        x1="1" y1="5" x2="21" y2="5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeDasharray={dash}
      />
    </svg>
  );
}

/**
 * Inline label editor. Click → opens a small popover with a text input;
 * Enter to commit, Esc to cancel. Empty input clears the label.
 */
function LabelEditor({
  edge,
  onSet,
}: {
  edge: { label: string };
  onSet: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(edge.label || "");
  useEffect(() => { if (open) setDraft(edge.label || ""); }, [open, edge.label]);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          title="Edit label"
          aria-label="Edit label"
          data-testid="edge-chip-label"
        >
          <Type className="size-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="center" sideOffset={6}>
        <div className="flex flex-col gap-2">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { onSet(draft); setOpen(false); }
              if (e.key === "Escape") setOpen(false);
            }}
            autoFocus
            placeholder="Edge label"
            className="w-48 rounded border border-neutral-300 px-2 py-1 text-sm outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-200"
          />
          <div className="flex items-center gap-2 text-[11px]">
            <button
              type="button"
              onClick={() => { onSet(draft); setOpen(false); }}
              className="rounded bg-sky-500 px-2 py-0.5 text-white hover:bg-sky-600"
            >
              Set
            </button>
            <button
              type="button"
              onClick={() => { onSet(""); setOpen(false); }}
              className="rounded px-2 py-0.5 text-neutral-600 hover:bg-neutral-100"
            >
              Clear
            </button>
            <Slash className="size-3 text-neutral-300" />
            <span className="text-neutral-500">Enter to save</span>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
