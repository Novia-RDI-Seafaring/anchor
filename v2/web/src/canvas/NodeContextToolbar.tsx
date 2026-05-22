/**
 * NodeContextToolbar — Miro-style floating mini-toolbar.
 *
 * Anchored above the bounding box of the currently selected nodes. The
 * toolbar replaces the auto-opened right Properties Panel: most edits
 * (label, body, spec rows, resize handles) already happen inline on the
 * node itself, so a slim action pill is the lighter affordance.
 *
 * Selection model: we read ReactFlow's own per-node `selected` flag via
 * `useStore` rather than introducing a parallel `selectedNodeIds` Set in
 * the UI store. This keeps Shift+click multi-select working out of the
 * box and avoids two sources of truth. The previous single-selection
 * `selectedNodeId` in uiStore still exists — it scopes the Properties
 * Panel, which is single-node by design.
 *
 * Positioning: the toolbar lives in screen-space (CSS `position: fixed`)
 * because anchoring it inside the React Flow viewport would force it to
 * scale with zoom. Re-positioned every time the viewport transform
 * changes (subscribing via `useStore((s) => s.transform)`) and whenever
 * the selection itself changes.
 *
 * Style chips: three small buttons surface Fill / Stroke / Text at the
 * top level — no nested Style submenu. Each chip is its own Radix
 * Popover, so they each have their own anchor and z-stack; the previous
 * "Style → Fill/Stroke" implementation shared a single anchor and the two
 * Radix Content layers collided.
 */
import { useReactFlow, useStore } from "@xyflow/react";
import {
  AlignCenter,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignStartHorizontal,
  AlignStartVertical,
  ChevronDown,
  Eye,
  Lock,
  MoreVertical,
  Move3d,
  Trash2,
  Unlock,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

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
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { DEFAULT_BG, resolveColors } from "./colors";
import { FillPicker } from "./FillPicker";
import { StrokePicker } from "./StrokePicker";
import { TextPicker } from "./TextPicker";

type Props = {
  workspaceSlug: string;
};

/** Local-storage flag — show the "(right-click for more)" hint once per session. */
const HINT_KEY = "anchor:nodeToolbar:hint-seen";

export function NodeContextToolbar({ workspaceSlug }: Props) {
  // Read ReactFlow's own selection state and viewport transform.
  const rfNodes = useStore((s) => s.nodes);
  const transform = useStore((s) => s.transform);
  const { flowToScreenPosition } = useReactFlow();

  const selectedNodeIds = useMemo(
    () => rfNodes.filter((n) => n.selected).map((n) => n.id),
    [rfNodes],
  );

  // Pull canonical node data (incl. width/height) from our own store so
  // the bounding box matches the actual rendered geometry.
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);

  // For "Organize ▾": only show when at least one selected node has an
  // edge touching it (mirrors OrganizeEditor's `hasChildren`). The
  // server-side organizer treats edges as undirected.
  const anySelectedHasEdges = useMemo(
    () => Object.values(edges).some((e) => selectedNodeIds.includes(e.source) || selectedNodeIds.includes(e.target)),
    [edges, selectedNodeIds],
  );

  // Compute the bounding box of the selection (screen space).
  const screenBox = useMemo(() => {
    if (selectedNodeIds.length === 0) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const id of selectedNodeIds) {
      const n = nodes[id];
      if (!n) continue;
      const w = (n.data?.width as number | undefined) ?? 100;
      const h = (n.data?.height as number | undefined) ?? 100;
      const tl = flowToScreenPosition({ x: n.x, y: n.y });
      const br = flowToScreenPosition({ x: n.x + w, y: n.y + h });
      if (tl.x < minX) minX = tl.x;
      if (tl.y < minY) minY = tl.y;
      if (br.x > maxX) maxX = br.x;
      if (br.y > maxY) maxY = br.y;
    }
    if (!isFinite(minX)) return null;
    return { left: minX, top: minY, right: maxX, bottom: maxY };
    // Re-anchor whenever the viewport transform changes (pan/zoom) — the
    // dep on `transform` is what does it. flowToScreenPosition itself is
    // stable across the lifetime of the provider.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeIds, nodes, transform]);

  const setPropertiesOpen = useUiStore((s) => s.setPropertiesOpen);

  // First-use hint — visible once per browser session.
  const [showHint, setShowHint] = useState<boolean>(() => {
    try { return window.localStorage.getItem(HINT_KEY) !== "1"; } catch { return false; }
  });
  useEffect(() => {
    if (!showHint || selectedNodeIds.length === 0) return;
    const t = window.setTimeout(() => {
      setShowHint(false);
      try { window.localStorage.setItem(HINT_KEY, "1"); } catch { /* noop */ }
    }, 4000);
    return () => window.clearTimeout(t);
  }, [showHint, selectedNodeIds.length]);

  // Inline delete confirmation toggle — spec says "Delete?" affordance,
  // not a modal.
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const confirmTimerRef = useRef<number | null>(null);
  // Auto-reset the "Delete?" confirm if the user wanders off.
  useEffect(() => {
    if (!confirmingDelete) return;
    confirmTimerRef.current = window.setTimeout(() => setConfirmingDelete(false), 3000);
    return () => {
      if (confirmTimerRef.current) window.clearTimeout(confirmTimerRef.current);
    };
  }, [confirmingDelete]);
  // Reset confirm state when the selection changes — we don't want a
  // stale "Delete?" hanging over a different selection.
  useEffect(() => { setConfirmingDelete(false); }, [selectedNodeIds.join(",")]);

  if (!screenBox || selectedNodeIds.length === 0) return null;

  const isMulti = selectedNodeIds.length > 1;
  const isTriPlus = selectedNodeIds.length >= 3;

  // For single-document selection, surface Open Viewer.
  const firstId = selectedNodeIds[0];
  const singleNode = selectedNodeIds.length === 1 && firstId ? nodes[firstId] ?? null : null;
  const isDocument = singleNode?.node_type === "document";

  // Chip visuals — derive from the first selected node's current `data`
  // so the chip itself reflects the live colour (Miro pattern). Multi-
  // select shows the first node's value; picks apply to all.
  const firstData = firstId ? nodes[firstId]?.data ?? {} : {};
  const { bg: firstBg, stroke: firstStroke } = resolveColors(firstData);
  const firstTextColor =
    (firstData as { text_color?: string }).text_color ?? firstStroke;
  const isLocked = (firstData as { locked?: boolean }).locked === true;

  const handleOrganize = async (orientation: "vertical" | "horizontal") => {
    // Use the first selected node as root — matches OrganizeEditor's
    // single-node convention. With multi-select, organising "everything"
    // isn't a defined op; we still pick the first id.
    if (!firstId) return;
    try {
      await canvases.organizeSubtree(workspaceSlug, firstId, orientation);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("organize failed", err);
    }
  };

  const handleAlign = async (anchor: "top" | "bottom" | "left" | "right" | "center-h" | "center-v") => {
    try {
      await canvases.align(workspaceSlug, selectedNodeIds, anchor);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("align failed", err);
    }
  };

  const handleDistribute = async (axis: "horizontal" | "vertical") => {
    try {
      await canvases.distribute(workspaceSlug, selectedNodeIds, axis);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("distribute failed", err);
    }
  };

  const handleDelete = async () => {
    for (const id of selectedNodeIds) {
      try {
        await canvases.removeNode(workspaceSlug, id);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("delete failed", err);
      }
    }
    setConfirmingDelete(false);
  };

  const toggleLock = async () => {
    const next = !isLocked;
    for (const id of selectedNodeIds) {
      const data = { ...(nodes[id]?.data ?? {}), locked: next };
      try {
        await canvases.patchNode(workspaceSlug, id, { data });
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("lock toggle failed", err);
      }
    }
  };

  const getNodeData = (nid: string) => nodes[nid]?.data;

  // Anchor toolbar above the box, with a small breathing gap.
  const TOOLBAR_OFFSET = 12;
  const style: React.CSSProperties = {
    position: "fixed",
    left: (screenBox.left + screenBox.right) / 2,
    top: Math.max(8, screenBox.top - TOOLBAR_OFFSET),
    transform: "translate(-50%, -100%)",
    zIndex: 30,
  };

  return (
    <div
      data-testid="node-context-toolbar"
      style={style}
      // Prevent the click that activates a toolbar button from also
      // landing on the canvas pane (which would deselect everything).
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <div className="flex items-center gap-1 rounded-md border border-neutral-200 bg-white px-1 py-1 shadow-md">
        {/* Organize ▾ — only when any selected node has an edge. Disabled
            for pure-multi selections without subtree semantics. */}
        {anySelectedHasEdges ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Organize subtree"
                title="Organize subtree"
              >
                <Move3d className="size-3.5" />
                <span className="text-[11px]">Organize</span>
                <ChevronDown className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center" sideOffset={6}>
              <DropdownMenuItem onSelect={() => void handleOrganize("vertical")}>
                Vertical
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => void handleOrganize("horizontal")}>
                Horizontal
              </DropdownMenuItem>
              <DropdownMenuItem disabled>
                Radial (coming soon)
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}

        {/* Open Viewer — single document node only. */}
        {isDocument && singleNode ? (
          <Button
            variant="ghost"
            size="sm"
            title="Open in viewer"
            aria-label="Open in viewer"
            onClick={() => {
              const slug = (singleNode.data as { slug?: string } | undefined)?.slug;
              if (slug) useUiStore.getState().openPdf(slug, {
                workspaceSlug,
                documentNodeId: singleNode.id,
              });
            }}
          >
            <Eye className="size-3.5" />
            <span className="text-[11px]">Open viewer</span>
          </Button>
        ) : null}

        {/* ────── Style chips ────── */}
        {/* Fill chip — square swatch tinted with current bg, falls back to
            transparent-checker visual when no fill is set. */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              data-testid="chip-fill"
              aria-label="Fill colour"
              title="Fill colour"
              className="inline-flex h-6 items-center gap-1 rounded border border-neutral-300 bg-white px-1.5 transition hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <ChipFillSwatch color={firstBg} />
              <ChevronDown className="size-3 text-neutral-500" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="center" sideOffset={6}>
            <FillPicker
              workspaceSlug={workspaceSlug}
              nodeIds={selectedNodeIds}
              getNodeData={getNodeData}
            />
          </PopoverContent>
        </Popover>

        {/* Stroke chip — filled circle tinted with current stroke. */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              data-testid="chip-stroke"
              aria-label="Stroke colour"
              title="Stroke colour"
              className="inline-flex h-6 items-center gap-1 rounded border border-neutral-300 bg-white px-1.5 transition hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <span
                className="block h-3.5 w-3.5 rounded-full border border-neutral-400"
                style={{ background: firstStroke }}
                aria-hidden
              />
              <ChevronDown className="size-3 text-neutral-500" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="center" sideOffset={6}>
            <StrokePicker
              workspaceSlug={workspaceSlug}
              nodeIds={selectedNodeIds}
              getNodeData={getNodeData}
            />
          </PopoverContent>
        </Popover>

        {/* Text chip — letter A with a coloured underline tint (Miro's A̲). */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              data-testid="chip-text"
              aria-label="Text style"
              title="Text style"
              className="inline-flex h-6 items-center gap-1 rounded border border-neutral-300 bg-white px-1.5 transition hover:bg-neutral-50 focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <span
                className="inline-flex h-4 w-4 items-center justify-center text-[11px] font-semibold leading-none text-neutral-700"
                aria-hidden
                style={{
                  borderBottom: `2px solid ${firstTextColor}`,
                  paddingBottom: 1,
                }}
              >
                A
              </span>
              <ChevronDown className="size-3 text-neutral-500" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="center" sideOffset={6}>
            <TextPicker
              workspaceSlug={workspaceSlug}
              nodeIds={selectedNodeIds}
              getNodeData={getNodeData}
            />
          </PopoverContent>
        </Popover>

        {/* Lock chip — toggles data.locked. */}
        <Button
          variant="ghost"
          size="icon"
          title={isLocked ? "Unlock" : "Lock"}
          aria-label={isLocked ? "Unlock node" : "Lock node"}
          aria-pressed={isLocked}
          onClick={() => void toggleLock()}
          data-testid="chip-lock"
          className={isLocked ? "bg-neutral-100 text-neutral-900" : undefined}
        >
          {isLocked ? <Lock className="size-3.5" /> : <Unlock className="size-3.5" />}
        </Button>

        {/* Multi-select alignment buttons. Distribute needs ≥3. */}
        {isMulti ? (
          <>
            <Button
              variant="ghost"
              size="icon"
              title="Align top"
              aria-label="Align top"
              onClick={() => void handleAlign("top")}
            >
              <AlignStartHorizontal className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Align bottom"
              aria-label="Align bottom"
              onClick={() => void handleAlign("bottom")}
            >
              <AlignEndHorizontal className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Align left"
              aria-label="Align left"
              onClick={() => void handleAlign("left")}
            >
              <AlignStartVertical className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Align right"
              aria-label="Align right"
              onClick={() => void handleAlign("right")}
            >
              <AlignEndVertical className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Center horizontally (share y midline)"
              aria-label="Center horizontally"
              onClick={() => void handleAlign("center-h")}
            >
              <AlignCenter className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title="Center vertically (share x midline)"
              aria-label="Center vertically"
              onClick={() => void handleAlign("center-v")}
            >
              <AlignCenterVertical className="size-3.5" />
            </Button>
            {isTriPlus ? (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  title="Distribute horizontally"
                  aria-label="Distribute horizontally"
                  onClick={() => void handleDistribute("horizontal")}
                >
                  <span className="text-[11px]">↔</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  title="Distribute vertically"
                  aria-label="Distribute vertically"
                  onClick={() => void handleDistribute("vertical")}
                >
                  <span className="text-[11px]">↕</span>
                </Button>
              </>
            ) : null}
          </>
        ) : null}

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
            title="Delete selection"
            aria-label="Delete selection"
            onClick={() => setConfirmingDelete(true)}
          >
            <Trash2 className="size-3.5" />
          </Button>
        )}

        {/* ⋮ More — open the right-side Properties Panel. */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              title="More actions"
              aria-label="More actions"
            >
              <MoreVertical className="size-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" sideOffset={6}>
            <DropdownMenuLabel>Actions</DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => {
              // Stamp single-node selection so the Properties Panel
              // resolves to the most-recently-clicked target.
              const last = selectedNodeIds[selectedNodeIds.length - 1] ?? null;
              useUiStore.getState().setSelectedNodeId(last);
              setPropertiesOpen(true);
            }}>
              Edit properties…
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>
              Bring to front (coming soon)
            </DropdownMenuItem>
            <DropdownMenuItem disabled>
              Send to back (coming soon)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {showHint ? (
        <div
          aria-hidden
          className="mt-1 select-none rounded bg-neutral-900/80 px-1.5 py-0.5 text-center text-[10px] text-white shadow"
        >
          right-click for more
        </div>
      ) : null}
    </div>
  );
}

/**
 * Fill chip swatch — square that's tinted with the current `bg_color`. When
 * the colour resolves to `transparent` (no fill) we render a tiny
 * checkered-transparent indicator so the user can tell "no fill" apart
 * from "white fill", matching Miro's visual vocabulary.
 */
function ChipFillSwatch({ color }: { color: string }) {
  const isTransparent = color === DEFAULT_BG || color === "transparent";
  if (isTransparent) {
    return (
      <span
        className="block h-3.5 w-3.5 rounded border border-neutral-400"
        style={{
          backgroundImage:
            "linear-gradient(45deg, #d4d4d4 25%, transparent 25%), " +
            "linear-gradient(-45deg, #d4d4d4 25%, transparent 25%), " +
            "linear-gradient(45deg, transparent 75%, #d4d4d4 75%), " +
            "linear-gradient(-45deg, transparent 75%, #d4d4d4 75%)",
          backgroundSize: "6px 6px",
          backgroundPosition: "0 0, 0 3px, 3px -3px, -3px 0px",
        }}
        aria-hidden
      />
    );
  }
  return (
    <span
      className="block h-3.5 w-3.5 rounded border border-neutral-400"
      style={{ background: color }}
      aria-hidden
    />
  );
}

