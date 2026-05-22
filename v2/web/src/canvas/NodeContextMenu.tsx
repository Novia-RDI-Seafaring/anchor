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
 * non-canvas use.
 *
 * Item enablement rules:
 *   - Fill / Stroke / Text — always (top-level submenus; producer
 *     primitives ignore the colour fields).
 *   - Align top/bottom/left/right/center-h/center-v — only when ≥ 2 selected
 *   - Distribute horizontal/vertical — only when ≥ 3 selected
 *   - Bring to front / Send to back — disabled today (pending a z-order field)
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
  PaintBucket,
  Sparkles,
  Type,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { FillPicker } from "./FillPicker";
import { StrokePicker } from "./StrokePicker";
import { TextPicker } from "./TextPicker";

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

type OpenSub = null | "organize" | "fill" | "stroke" | "text";

export function NodeContextMenu({ workspaceSlug, target, onClose }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [openSub, setOpenSub] = useState<OpenSub>(null);
  // Read canvas store for the picker's `getNodeData` lookup. Hooks
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
  // single node to the selection in onNodeContextMenu. We still
  // defensively include nodeId.
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

  // Toggle placeholder mode across the selection. If *any* node in the
  // selection is already a placeholder we clear them all; otherwise we
  // mark them all. Idempotent + obvious.
  const anyPlaceholder = ids.some(
    (nid) => (storeNodes[nid]?.data as { placeholder?: unknown } | undefined)?.placeholder === true,
  );
  const togglePlaceholder = () =>
    runAndClose(async () => {
      for (const nid of ids) {
        const existing = (storeNodes[nid]?.data ?? {}) as Record<string, unknown>;
        const nextData = { ...existing, placeholder: !anyPlaceholder };
        if (anyPlaceholder) {
          // Clearing — drop the hint too so the node returns to a clean state.
          delete (nextData as { placeholder_hint?: unknown }).placeholder_hint;
        }
        await canvases.patchNode(workspaceSlug, nid, { data: nextData });
      }
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
      style={{
        position: "fixed",
        left: target.x,
        top: target.y,
        zIndex: 60,
      }}
      className="min-w-[12rem] overflow-visible rounded-md border border-neutral-200 bg-white p-1 text-neutral-700 shadow-lg"
    >
      {/* ────── Top-level style submenus (Fill / Stroke / Text) ──────
          These used to live under a single "Style ▸" submenu. Flattening
          them to the top level matches the toolbar's chip vocabulary and
          avoids the two-level nesting that caused popover-stacking bugs. */}
      <SubmenuRow
        open={openSub === "fill"}
        onEnter={() => setOpenSub("fill")}
        onLeave={(e, container) => {
          // Only collapse when the cursor leaves the row AND its open panel.
          if (!container.contains(e.relatedTarget as Node | null)) setOpenSub(null);
        }}
        renderTrigger={() => (
          <MenuItem
            icon={<PaintBucket className="size-3.5" />}
            rightAdornment={<ChevronRight className="size-3" />}
          >
            Fill
          </MenuItem>
        )}
        renderPanel={() => (
          <FillPicker
            workspaceSlug={workspaceSlug}
            nodeIds={ids}
            getNodeData={(nid) => storeNodes[nid]?.data}
            onClose={onClose}
          />
        )}
      />
      <SubmenuRow
        open={openSub === "stroke"}
        onEnter={() => setOpenSub("stroke")}
        onLeave={(e, container) => {
          if (!container.contains(e.relatedTarget as Node | null)) setOpenSub(null);
        }}
        renderTrigger={() => (
          <MenuItem
            icon={<Palette className="size-3.5" />}
            rightAdornment={<ChevronRight className="size-3" />}
          >
            Stroke
          </MenuItem>
        )}
        renderPanel={() => (
          <StrokePicker
            workspaceSlug={workspaceSlug}
            nodeIds={ids}
            getNodeData={(nid) => storeNodes[nid]?.data}
            onClose={onClose}
          />
        )}
      />
      <SubmenuRow
        open={openSub === "text"}
        onEnter={() => setOpenSub("text")}
        onLeave={(e, container) => {
          if (!container.contains(e.relatedTarget as Node | null)) setOpenSub(null);
        }}
        renderTrigger={() => (
          <MenuItem
            icon={<Type className="size-3.5" />}
            rightAdornment={<ChevronRight className="size-3" />}
          >
            Text
          </MenuItem>
        )}
        renderPanel={() => (
          <TextPicker
            workspaceSlug={workspaceSlug}
            nodeIds={ids}
            getNodeData={(nid) => storeNodes[nid]?.data}
            onClose={onClose}
          />
        )}
      />
      <Separator />

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
      <MenuItem disabled>Bring to front (coming soon)</MenuItem>
      <MenuItem disabled>Send to back (coming soon)</MenuItem>
      <Separator />
      <SubmenuRow
        open={openSub === "organize"}
        onEnter={() => target.hasEdges && setOpenSub("organize")}
        onLeave={(e, container) => {
          if (!container.contains(e.relatedTarget as Node | null)) setOpenSub(null);
        }}
        renderTrigger={() => (
          <MenuItem
            disabled={!target.hasEdges}
            rightAdornment={<ChevronRight className="size-3" />}
          >
            Organize subtree
          </MenuItem>
        )}
        renderPanel={() =>
          target.hasEdges ? (
            <div className="min-w-[8rem]">
              <MenuItem onClick={() => void organize("vertical")}>Vertical</MenuItem>
              <MenuItem onClick={() => void organize("horizontal")}>Horizontal</MenuItem>
              <MenuItem disabled>Radial (coming soon)</MenuItem>
            </div>
          ) : null
        }
      />
      <Separator />
      <MenuItem
        icon={<Sparkles className="size-3.5" />}
        onClick={() => void togglePlaceholder()}
      >
        {anyPlaceholder ? "Clear placeholder" : "Mark as placeholder"}
      </MenuItem>
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

/**
 * SubmenuRow — generic mouse-driven submenu container. Used for the four
 * top-level "▸" entries (Fill / Stroke / Text / Organize). Owns the
 * `relative` positioning and the absolute-anchored panel; the caller
 * supplies the trigger and the panel contents.
 *
 * The previous Style submenu shared a `relative` wrapper with both the
 * Fill picker and the Stroke picker, which made Radix layer the two
 * Content surfaces at the same anchor + z-index. Flattening to top level
 * AND giving each submenu its own wrapper restores per-panel anchoring.
 */
function SubmenuRow({
  open, onEnter, onLeave, renderTrigger, renderPanel,
}: {
  open: boolean;
  onEnter: () => void;
  onLeave: (e: React.MouseEvent, container: HTMLDivElement) => void;
  renderTrigger: () => React.ReactNode;
  renderPanel: () => React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  return (
    <div
      ref={containerRef}
      className="relative"
      onMouseEnter={onEnter}
      onMouseLeave={(e) => {
        if (containerRef.current) onLeave(e, containerRef.current);
      }}
    >
      {renderTrigger()}
      {open ? (
        <div className="absolute left-full top-0 ml-1 rounded-md border border-neutral-200 bg-white p-2 shadow-md">
          {renderPanel()}
        </div>
      ) : null}
    </div>
  );
}

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
