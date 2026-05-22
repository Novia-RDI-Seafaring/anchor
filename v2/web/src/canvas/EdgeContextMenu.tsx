/**
 * EdgeContextMenu — right-click affordance for canvas edges. Mirrors
 * `NodeContextMenu`'s layout and gestures but with edge-specific items.
 *
 * Top-level rows: Route ▸ / Start ▸ / End ▸ / Style ▸ / Stroke colour ▸
 * (all single-level submenus — no nested levels), then Set label…,
 * Lock, separator, Delete, Edit data….
 *
 * Selection model: ReactFlow's `onEdgeContextMenu` hands us the target
 * edge. We stash the screen coordinates + edge id and render a fixed
 * panel. Closing happens on Esc / outside-click / item-select.
 */
import { ChevronRight, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { canvases } from "@/api/canvases";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { STROKE_SWATCHES } from "./colors";
import {
  resolveEdgeUserStyle,
  type EdgeCap,
  type EdgeStrokeStyle,
} from "./edges/edge-style";

export type EdgeContextMenuTarget = {
  x: number;
  y: number;
  edgeId: string;
};

type Props = {
  workspaceSlug: string;
  target: EdgeContextMenuTarget | null;
  onClose: () => void;
};

type OpenSub = null | "route" | "start" | "end" | "style" | "color";

export function EdgeContextMenu({ workspaceSlug, target, onClose }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [openSub, setOpenSub] = useState<OpenSub>(null);
  const edges = useCanvasStore((s) => s.edges);

  useEffect(() => {
    if (!target) return;
    const onKey = (ev: KeyboardEvent) => { if (ev.key === "Escape") onClose(); };
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
  const edge = edges[target.edgeId];
  if (!edge) return null;

  const user = resolveEdgeUserStyle(edge.data);

  const patch = async (fields: Record<string, unknown>) => {
    try { await canvases.patchEdge(workspaceSlug, edge.id, fields); }
    catch (err) {
      // eslint-disable-next-line no-console
      console.error("edge patch failed", err);
    }
  };
  const patchData = (changes: Record<string, unknown>) =>
    patch({ data: { ...(edge.data ?? {}), ...changes } });

  const runAndClose = async (fn: () => Promise<void>) => {
    try { await fn(); } finally { onClose(); }
  };

  const setRoute = (mode: "floating" | "smooth" | "step" | "straight") =>
    runAndClose(async () => { await patch({ edge_type: mode }); });
  const setCap = (which: "start_marker" | "end_marker", value: EdgeCap) =>
    runAndClose(async () => { await patchData({ [which]: value }); });
  const setStyle = (s: EdgeStrokeStyle) =>
    runAndClose(async () => { await patchData({ stroke_style: s }); });
  const setColor = (c: string | undefined) =>
    runAndClose(async () => { await patchData({ stroke_color: c }); });
  const remove = () =>
    runAndClose(async () => {
      await canvases.removeEdge(workspaceSlug, edge.id);
      useUiStore.getState().setSelectedEdgeId(null);
    });
  const setLabelPrompt = () => {
    const next = window.prompt("Edge label:", edge.label || "");
    if (next == null) { onClose(); return; }
    void runAndClose(async () => { await patch({ label: next }); });
  };
  const toggleLock = () =>
    runAndClose(async () => { await patchData({ locked: !user.locked }); });
  const editDataJson = () => {
    const current = JSON.stringify(edge.data ?? {}, null, 2);
    const next = window.prompt("Edit edge data (JSON):", current);
    if (next == null) { onClose(); return; }
    try {
      const parsed = JSON.parse(next);
      if (parsed && typeof parsed === "object") {
        void runAndClose(async () => { await patch({ data: parsed }); });
        return;
      }
    } catch {
      window.alert("Invalid JSON; edit cancelled.");
    }
    onClose();
  };

  return (
    <div
      ref={ref}
      role="menu"
      data-testid="edge-context-menu"
      style={{ position: "fixed", left: target.x, top: target.y, zIndex: 60 }}
      className="min-w-[12rem] overflow-visible rounded-md border border-neutral-200 bg-white p-1 text-neutral-700 shadow-lg"
    >
      <SubmenuRow
        open={openSub === "route"}
        onEnter={() => setOpenSub("route")}
        onLeave={(e, c) => { if (!c.contains(e.relatedTarget as Node | null)) setOpenSub(null); }}
        renderTrigger={() => <MenuItem rightAdornment={<ChevronRight className="size-3" />}>Route</MenuItem>}
        renderPanel={() => (
          <div className="min-w-[8rem]">
            <MenuItem onClick={() => void setRoute("floating")}>Floating</MenuItem>
            <MenuItem onClick={() => void setRoute("smooth")}>Smooth</MenuItem>
            <MenuItem onClick={() => void setRoute("step")}>Step</MenuItem>
            <MenuItem onClick={() => void setRoute("straight")}>Straight</MenuItem>
          </div>
        )}
      />
      <SubmenuRow
        open={openSub === "start"}
        onEnter={() => setOpenSub("start")}
        onLeave={(e, c) => { if (!c.contains(e.relatedTarget as Node | null)) setOpenSub(null); }}
        renderTrigger={() => <MenuItem rightAdornment={<ChevronRight className="size-3" />}>Start</MenuItem>}
        renderPanel={() => (
          <div className="min-w-[8rem]">
            <MenuItem onClick={() => void setCap("start_marker", "none")}>None</MenuItem>
            <MenuItem onClick={() => void setCap("start_marker", "arrow")}>Arrow</MenuItem>
            <MenuItem onClick={() => void setCap("start_marker", "circle")}>Circle</MenuItem>
          </div>
        )}
      />
      <SubmenuRow
        open={openSub === "end"}
        onEnter={() => setOpenSub("end")}
        onLeave={(e, c) => { if (!c.contains(e.relatedTarget as Node | null)) setOpenSub(null); }}
        renderTrigger={() => <MenuItem rightAdornment={<ChevronRight className="size-3" />}>End</MenuItem>}
        renderPanel={() => (
          <div className="min-w-[8rem]">
            <MenuItem onClick={() => void setCap("end_marker", "none")}>None</MenuItem>
            <MenuItem onClick={() => void setCap("end_marker", "arrow")}>Arrow</MenuItem>
            <MenuItem onClick={() => void setCap("end_marker", "circle")}>Circle</MenuItem>
          </div>
        )}
      />
      <SubmenuRow
        open={openSub === "style"}
        onEnter={() => setOpenSub("style")}
        onLeave={(e, c) => { if (!c.contains(e.relatedTarget as Node | null)) setOpenSub(null); }}
        renderTrigger={() => <MenuItem rightAdornment={<ChevronRight className="size-3" />}>Style</MenuItem>}
        renderPanel={() => (
          <div className="min-w-[8rem]">
            <MenuItem onClick={() => void setStyle("solid")}>Solid</MenuItem>
            <MenuItem onClick={() => void setStyle("dashed")}>Dashed</MenuItem>
            <MenuItem onClick={() => void setStyle("dotted")}>Dotted</MenuItem>
          </div>
        )}
      />
      <SubmenuRow
        open={openSub === "color"}
        onEnter={() => setOpenSub("color")}
        onLeave={(e, c) => { if (!c.contains(e.relatedTarget as Node | null)) setOpenSub(null); }}
        renderTrigger={() => <MenuItem rightAdornment={<ChevronRight className="size-3" />}>Stroke colour</MenuItem>}
        renderPanel={() => (
          <div className="flex flex-col gap-2 min-w-[12rem]">
            <div className="flex flex-wrap items-center gap-1">
              {STROKE_SWATCHES.map((sw) => (
                <button
                  key={`menu-color-${sw.label}`}
                  type="button"
                  role="menuitem"
                  aria-label={`stroke ${sw.label}`}
                  title={sw.label}
                  onClick={() => void setColor(sw.stroke)}
                  className="h-5 w-5 rounded-full border border-neutral-300 transition hover:scale-110 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  style={{ background: sw.stroke }}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={() => void setColor(undefined)}
              className="rounded px-1.5 py-0.5 text-left text-[11px] text-neutral-600 hover:bg-neutral-100"
            >
              Reset
            </button>
          </div>
        )}
      />
      <Separator />
      <MenuItem onClick={setLabelPrompt}>Set label…</MenuItem>
      <MenuItem onClick={() => void toggleLock()}>
        {user.locked ? "Unlock" : "Lock"}
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
      <MenuItem onClick={editDataJson}>Edit data…</MenuItem>
    </div>
  );
}

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
      onMouseLeave={(e) => { if (containerRef.current) onLeave(e, containerRef.current); }}
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

function Separator() {
  return <div className="my-1 h-px bg-neutral-200" aria-hidden />;
}
