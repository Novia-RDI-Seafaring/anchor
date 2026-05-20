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
 * Hidden by default (renders null) when fewer than one node is selected.
 * Hidden when only one node is selected for *alignment* buttons; those
 * buttons appear from two-node selections upward.
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
  MoreVertical,
  Move3d,
  Trash2,
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
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

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

        {/* Open Viewer — single document node only. */}
        {isDocument && singleNode ? (
          <Button
            variant="ghost"
            size="icon"
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
          </Button>
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
