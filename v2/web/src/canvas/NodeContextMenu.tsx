/**
 * NodeContextMenu — right-click affordance for canvas nodes.
 *
 * ReactFlow's `onNodeContextMenu` callback fires the browser's native
 * contextmenu event suppression for us, then hands us the screen
 * coordinates plus the target node. We render a small floating menu
 * anchored at the cursor. Closing happens on:
 *   - Esc key
 *   - outside-click (document-level pointerdown listener)
 *   - selecting an item
 *
 * Why we don't reuse the Radix ContextMenu primitive in
 * `components/ui/context-menu.tsx` here: Radix v2 attaches the open
 * gesture to a `Trigger` element (a right-click on the trigger fires
 * the menu). ReactFlow intercepts the contextmenu event on nodes and
 * gives us a callback — there's no DOM element we can hand to Radix as
 * the trigger without re-implementing the right-click ourselves. A
 * tiny hand-rolled menu is simpler than fighting the abstraction. The
 * Radix primitive in `ui/context-menu.tsx` is kept for any future
 * non-canvas use (e.g. a right-click on a card in the LibraryDrawer).
 *
 * Item enablement rules (mirror the spec):
 *   - Align top/bottom/left/right/center-h/center-v — only when ≥ 2 selected
 *   - Distribute horizontal/vertical — only when ≥ 3 selected
 *   - Bring to front / Send to back — single or multi (disabled today,
 *     pending a z-order field on Node — TODO note inline)
 *   - Organize subtree — single node OR multi if any selected has edges
 *   - Delete / Edit properties — always
 */
import {
  AlignCenter,
  AlignCenterVertical,
  AlignEndHorizontal,
  AlignEndVertical,
  AlignStartHorizontal,
  AlignStartVertical,
  ChevronRight,
  Palette,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { StylePicker } from "./StylePicker";

export type ContextMenuTarget = {
  /** Screen coordinates of the click. */
  x: number;
  y: number;
  /** The right-clicked node's id (the gesture origin). */
  nodeId: string;
  /** All currently-selected node ids — includes nodeId if it's part of
   *  the multi-select. */
  selectedIds: string[];
  /** True when the right-clicked node touches at least one edge. Drives
   *  the "Organize subtree" enablement. */
  hasEdges: boolean;
};

type Props = {
  workspaceSlug: string;
  target: ContextMenuTarget | null;
  onClose: () => void;
};

export function NodeContextMenu({ workspaceSlug, target, onClose }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [styleOpen, setStyleOpen] = useState(false);
  // Read canvas store for the StylePicker's `getNodeData` lookup. Hooks
  // can't live conditionally, so we always subscribe even when the menu
  // is closed.
  const storeNodes = useCanvasStore((s) => s.nodes);

  useEffect(() => {
    if (!target) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") onClose();
    };
    const onDown = (ev: PointerEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(ev.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown, true);
    };
  }, [target, onClose]);

  if (!target) return null;

  // Effective selection — if the user right-clicked a node that *isn't*
  // already in the multi-select, ReactFlow has already promoted that
  // single node to the selection in onNodeContextMenu (by emitting a
  // dimensions/select change). We still defensively include nodeId.
  const ids = target.selectedIds.length > 0 ? target.selectedIds : [target.nodeId];
  const multi = ids.length >= 2;
  const triPlus = ids.length >= 3;

  const runAndClose = async (fn: () => Promise<void>) => {
    try {
      await fn();
    } finally {
      onClose();
    }
  };

  const align = (anchor: "top" | "bottom" | "left" | "right" | "center-h" | "center-v") =>
    runAndClose(async () => { await canvases.align(workspaceSlug, ids, anchor); });
  const distribute = (axis: "horizontal" | "vertical") =>
    runAndClose(async () => { await canvases.distribute(workspaceSlug, ids, axis); });
  const organize = (orientation: "vertical" | "horizontal") =>
    runAndClose(async () => { await canvases.organizeSubtree(workspaceSlug, target.nodeId, orientation); });
  const remove = () =>
    runAndClose(async () => {
      for (const id of ids) await canvases.removeNode(workspaceSlug, id);
    });
  const openProperties = () => {
    useUiStore.getState().setSelectedNodeId(target.nodeId);
    useUiStore.getState().setPropertiesOpen(true);
    onClose();
  };

  return (
    <div
      ref={ref}
      role="menu"
      data-testid="node-context-menu"
      // Anchor at the click point; the menu uses a fixed-position float
      // because the canvas is full-bleed.
      style={{
        position: "fixed",
        left: target.x,
        top: target.y,
        zIndex: 60,
      }}
      className="min-w-[12rem] overflow-visible rounded-md border border-neutral-200 bg-white p-1 text-neutral-700 shadow-lg"
    >
      <MenuLabel>Align</MenuLabel>
      <MenuItem disabled={!multi} icon={<AlignStartHorizontal className="size-3.5" />} onClick={() => void align("top")}>
        Top
      </MenuItem>
      <MenuItem disabled={!multi} icon={<AlignEndHorizontal className="size-3.5" />} onClick={() => void align("bottom")}>
        Bottom
      </MenuItem>
      <MenuItem disabled={!multi} icon={<AlignStartVertical className="size-3.5" />} onClick={() => void align("left")}>
        Left
      </MenuItem>
      <MenuItem disabled={!multi} icon={<AlignEndVertical className="size-3.5" />} onClick={() => void align("right")}>
        Right
      </MenuItem>
      <MenuItem disabled={!multi} icon={<AlignCenter className="size-3.5" />} onClick={() => void align("center-h")}>
        Center horizontally
      </MenuItem>
      <MenuItem disabled={!multi} icon={<AlignCenterVertical className="size-3.5" />} onClick={() => void align("center-v")}>
        Center vertically
      </MenuItem>
      <Separator />
      <MenuLabel>Distribute</MenuLabel>
      <MenuItem disabled={!triPlus} onClick={() => void distribute("horizontal")}>
        Horizontally
      </MenuItem>
      <MenuItem disabled={!triPlus} onClick={() => void distribute("vertical")}>
        Vertically
      </MenuItem>
      <Separator />
      {/* Bring to front / Send to back — TODO: needs a z-order field on
          Node; deferred until that lands. Items rendered disabled so the
          eventual feature has a discoverable home. */}
      <MenuItem disabled>Bring to front</MenuItem>
      <MenuItem disabled>Send to back</MenuItem>
      <Separator />
      <div
        className="relative"
        onMouseEnter={() => setOrganizeOpen(true)}
        onMouseLeave={() => setOrganizeOpen(false)}
      >
        <MenuItem
          disabled={!target.hasEdges}
          onClick={() => setOrganizeOpen((o) => !o)}
          rightAdornment={<ChevronRight className="size-3" />}
        >
          Organize subtree
        </MenuItem>
        {organizeOpen && target.hasEdges ? (
          <div
            className="absolute left-full top-0 ml-1 min-w-[8rem] rounded-md border border-neutral-200 bg-white p-1 shadow-md"
            role="menu"
          >
            <MenuItem onClick={() => void organize("vertical")}>Vertical</MenuItem>
            <MenuItem onClick={() => void organize("horizontal")}>Horizontal</MenuItem>
            <MenuItem disabled>Radial (coming soon)</MenuItem>
          </div>
        ) : null}
      </div>
      {/* Style submenu — fill + stroke pickers. Same picker is reused on the
          mini-toolbar's ⋮ More overflow. Always enabled; on producer
          primitives the colour fields are just ignored. */}
      <div
        className="relative"
        onMouseEnter={() => setStyleOpen(true)}
        onMouseLeave={() => setStyleOpen(false)}
      >
        <MenuItem
          icon={<Palette className="size-3.5" />}
          onClick={() => setStyleOpen((o) => !o)}
          rightAdornment={<ChevronRight className="size-3" />}
        >
          Style
        </MenuItem>
        {styleOpen ? (
          <div className="absolute left-full top-0 ml-1">
            <StylePicker
              workspaceSlug={workspaceSlug}
              nodeIds={ids}
              getNodeData={(nid) => storeNodes[nid]?.data}
              onClose={onClose}
            />
          </div>
        ) : null}
      </div>
      <Separator />
      <MenuItem
        icon={<Trash2 className="size-3.5" />}
        onClick={() => void remove()}
        className="text-red-700 hover:bg-red-50"
      >
        Delete
      </MenuItem>
      <Separator />
      <MenuItem onClick={openProperties}>Edit properties…</MenuItem>
    </div>
  );
}

// ─── small primitives ─────────────────────────────────────────────────────

function MenuItem({
  children, icon, disabled, onClick, rightAdornment, className,
}: {
  children: React.ReactNode;
  icon?: React.ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  rightAdornment?: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-[12px] outline-none transition",
        "hover:bg-neutral-100 focus:bg-neutral-100 focus:text-neutral-900",
        disabled && "pointer-events-none opacity-50",
        className,
      )}
    >
      <span className="flex items-center gap-1.5">
        {icon}
        <span>{children}</span>
      </span>
      {rightAdornment}
    </button>
  );
}

function MenuLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
      {children}
    </div>
  );
}

function Separator() {
  return <div className="my-1 h-px bg-neutral-200" aria-hidden />;
}
