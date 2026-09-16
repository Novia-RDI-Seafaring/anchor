import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import type { OnResize, OnResizeEnd, OnResizeStart } from "@xyflow/react";
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { resolveText, SIZE_PX, type TextSize } from "@/canvas/colors";
import { ReviewBadge } from "@/canvas/ReviewBadge";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * TextNode — words on the canvas, with no card around them.
 *
 * Every other element is a container with a border, a background and a
 * heading. That is right for a fact or a spec and wrong for a title, a
 * caption, or a paragraph of explanation: those were being written into a
 * card and read as one more box. This is the Excalidraw text element.
 *
 * Renders `data.text` alone at the element's text size, with no chrome. It
 * honours the shared text keys (`text_size`, `text_color`, `text_bold`,
 * `text_align`, `text_family`), so a heading is a text element at `2xl` and
 * a caption is one at `sm`. Double-click to edit, Enter commits, Shift+Enter
 * makes a new line, Escape cancels.
 */
export function TextNode({ id, data, selected }: NodeProps) {
  const d = data as {
    text?: string;
    label?: string;
    width?: number;
    height?: number;
  };
  // `label` is accepted as a fallback so an agent that sets the usual field
  // still gets something on screen.
  const text = d.text ?? d.label ?? "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const t = resolveText(d as Record<string, unknown>);
  const edit = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: text,
    field: "text",
    multiline: true,
    canEdit: selected ?? false,
    // A text element has no label, so its body claims the focus stamp a
    // freshly placed element carries: place it and type.
    claimsPendingFocus: true,
  });
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );

  // Resizing text scales the words, as in Excalidraw: drag a corner and the
  // font grows with the box rather than the same words re-wrapping inside a
  // bigger frame. The scale is live during the drag and written once on
  // release, as `font_px` (a size between the buckets).
  const basePx =
    typeof (d as { font_px?: number }).font_px === "number"
      ? (d as { font_px: number }).font_px
      : SIZE_PX[((d as { text_size?: TextSize }).text_size ?? "md")];
  const [liveScale, setLiveScale] = useState(1);
  const startRef = useRef<{ height: number; px: number } | null>(null);

  const onResizeStart: OnResizeStart = (event, params) => {
    startRef.current = { height: params.height || 1, px: basePx };
    setLiveScale(1);
    resizeHandlers.onResizeStart(event, params);
  };
  const onResize: OnResize = (event, params) => {
    const start = startRef.current;
    if (start) setLiveScale(Math.max(0.2, params.height / start.height));
    resizeHandlers.onResize(event, params);
  };
  const onResizeEnd: OnResizeEnd = (event, params) => {
    const start = startRef.current;
    startRef.current = null;
    resizeHandlers.onResizeEnd(event, params);
    setLiveScale(1);
    if (!start || !workspaceSlug) return;
    const next = Math.round(Math.min(200, Math.max(6, start.px * (params.height / start.height))));
    // One patch for the whole gesture: the box and the size of the words.
    void canvases
      .patchNode(workspaceSlug, id, {
        data: { width: params.width, height: params.height, font_px: next },
      })
      .catch(() => {
        // SSE reconciles.
      });
  };
  const fontSize = liveScale === 1 ? t.fontSize : `${Math.round(basePx * liveScale)}px`;

  return (
    <div
      className={`relative ${selected ? "cursor-move" : "cursor-pointer"}`}
      style={{
        // No border and no background: the words are the element. A width
        // wraps the text; without one it sizes to its content.
        ...(liveW ? { width: liveW } : { maxWidth: "40rem" }),
        ...(liveH ? { minHeight: liveH } : {}),
        color: t.color,
        fontWeight: t.fontWeight,
        textAlign: t.textAlign,
        fontFamily: t.fontFamily,
        fontSize,
        lineHeight: 1.25,
      }}
      data-testid="text-node"
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={60}
        minHeight={24}
        color="#0ea5e9"
        // Corner-only, proportional: dragging a side would stretch the words.
        keepAspectRatio
        onResizeStart={onResizeStart}
        onResize={onResize}
        onResizeEnd={onResizeEnd}
      />
      <ReviewBadge data={data as Record<string, unknown>} nodeId={id} />
      <Handle type="target" position={Position.Left} />
      {edit.editing ? (
        <textarea
          {...edit.inputProps}
          // Edited in place: no box, no background, no outline. The words
          // stay where they were, at the same size and colour, with only a
          // caret to say you are typing. A bordered input over the canvas
          // reads as a form, which is not what writing on a canvas is.
          className={`${edit.inputProps.className} w-full resize-none border-0 bg-transparent p-0 outline-none focus:outline-none`}
          style={{
            fontSize,
            fontFamily: t.fontFamily,
            fontWeight: t.fontWeight,
            textAlign: t.textAlign,
            color: t.color,
            lineHeight: 1.25,
            // Grow with the text rather than scrolling inside a fixed box.
            overflow: "hidden",
            minHeight: "1.25em",
          }}
          placeholder="type"
        />
      ) : (
        <div
          className="whitespace-pre-wrap break-words"
          onDoubleClick={(e) => {
            e.stopPropagation();
            edit.beginEdit();
          }}
          title={selected ? "double-click to edit" : undefined}
        >
          {text || (
            <span className="italic opacity-40">
              {selected ? "double-click to write" : "text"}
            </span>
          )}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
