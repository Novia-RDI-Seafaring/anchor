import { NodeResizer, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { DEFAULT_BG, DEFAULT_STROKE, resolveColors, resolveText } from "@/canvas/colors";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";
import { useUiStore } from "@/stores/uiStore";

/**
 * AreaNode — labelled, dashed rounded-rectangle container.
 *
 * Renders a region with a title strip at the top, used to visually group
 * other nodes (subgraph). Set `data.label` for the title; `data.tone`
 * picks an accent style; `data.dashed` defaults to true (areas are always
 * dashed) but can be set to false for a solid container if needed.
 *
 * Areas use the rail's drag-out width/height by default but resize freely
 * via NodeResizer once placed. Inline rename is selection-gated.
 *
 * Note: ReactFlow renders areas with `selectable: false` (see
 * `CanvasGraph.toRfNode`) so they sit behind other nodes. The
 * `NodeResizer` runs off the `selected` prop, which is still set by
 * ReactFlow even though the area can't be picked by drag-rectangle. For
 * the resize handles to appear, callers will need to set `selectable:
 * true` on areas in a follow-up; for now the area lives at its drop-time
 * size and resizes via the Properties panel.
 */
export function AreaNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    width?: number;
    height?: number;
    tone?: string;
    dashed?: boolean;
    subtitle?: string;
    bg_color?: string;
    stroke_color?: string;
  };
  const label = d.label ?? "";
  // Live-resize mirror — see ConceptNode for the rationale.
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const w = liveW ?? 320;
  const h = liveH ?? 200;
  const dashed = d.dashed !== false;
  const toneClass: Record<string, string> = {
    sources: "border-neutral-500/70 bg-neutral-50",
    producers: "border-neutral-500/70 bg-neutral-50",
    durable: "border-neutral-500/70 bg-neutral-50",
    consumers: "border-neutral-500/70 bg-neutral-50",
    core: "border-neutral-500/70 bg-neutral-50",
    default: "border-neutral-400 bg-white/40",
  };
  const tone = toneClass[d.tone ?? "default"] ?? toneClass.default;
  const borderStyle = dashed ? "border-dashed" : "border-solid";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  // Drop-target highlight — CanvasGraph's onNodeDrag stashes the Area id
  // the cursor is hovering inside on uiStore.dropTargetAreaId. When it
  // matches THIS area, we render a brighter dashed border + a soft sky
  // tint so the user knows "release here = nest into this container".
  const isDropTarget = useUiStore((s) => s.dropTargetAreaId === id);
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
  });
  // Style picker overrides: inline `style` always wins over the `tone`
  // Tailwind classes. When the user hasn't picked anything we leave the
  // tone classes to draw the colour (DEFAULT_BG / DEFAULT_STROKE are
  // sentinel-only, applied via `inherit` to keep the original look).
  const { bg, stroke } = resolveColors(d);
  // Area labels resolve their text style through resolveText so the Text
  // chip works here too. We DO NOT modify the drop-target highlight logic
  // (the dashed-border + sky tint) below — only the label rendering.
  const t = resolveText(d);
  const styleOverride: React.CSSProperties = {
    width: w,
    height: h,
  };
  if (bg !== DEFAULT_BG) styleOverride.background = bg;
  if (stroke !== DEFAULT_STROKE) {
    styleOverride.borderColor = stroke;
    styleOverride.color = stroke;
  }
  // Drop-target visual: brighter sky border + soft sky fill + inner glow.
  // The transition smooths the highlight on/off so a fast hover doesn't
  // strobe. We OVERRIDE borderColor/background here so the highlight wins
  // even when the user has picked a custom stroke/bg via the style picker
  // — the highlight is a transient UX state, not a persisted choice.
  const dropStyle: React.CSSProperties = isDropTarget
    ? {
        borderColor: "#0ea5e9",
        background: "rgba(186, 230, 253, 0.35)",
        boxShadow: "inset 0 0 0 2px rgba(14, 165, 233, 0.25)",
        transition: "border-color 150ms ease, background 150ms ease, box-shadow 150ms ease",
      }
    : {
        transition: "border-color 150ms ease, background 150ms ease, box-shadow 150ms ease",
      };
  return (
    <div
      className={`pointer-events-auto rounded-xl border-2 ${borderStyle} ${tone}`}
      style={{ ...styleOverride, ...dropStyle }}
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={120}
        minHeight={60}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <div className="border-b border-current/20 px-3 py-1.5">
        {rename.editing ? (
          <input
            {...rename.inputProps}
            className={`${rename.inputProps.className} w-full rounded border border-neutral-300 bg-white px-1 py-0 text-[10px] font-semibold uppercase tracking-[0.18em] text-neutral-700 outline-none focus:border-neutral-500`}
            placeholder="label"
          />
        ) : (
          <div
            className={`text-[10px] uppercase tracking-[0.18em] text-neutral-700 ${selected ? "cursor-text" : "cursor-pointer"}`}
            style={{
              // Only override colour when the user has explicitly picked
              // one — otherwise the neutral-700 cascade carries the look.
              ...((d as { text_color?: string }).text_color
                ? { color: t.color }
                : {}),
              fontWeight: Math.max(t.fontWeight, 600),
              textAlign: t.textAlign,
              fontFamily: t.fontFamily,
            }}
            onDoubleClick={(e) => {
              e.stopPropagation();
              rename.beginEdit();
            }}
            title={selected ? "double-click to rename" : undefined}
          >
            {label || <span className="font-normal italic tracking-normal text-neutral-400">untitled · double-click to name</span>}
          </div>
        )}
        {d.subtitle ? (
          <div className="text-[10px] italic text-neutral-500">{d.subtitle}</div>
        ) : null}
      </div>
    </div>
  );
}
