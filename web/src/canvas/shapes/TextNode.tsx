import { Handle, NodeResizer, Position, useReactFlow, type NodeProps } from "@xyflow/react";
import type { OnResize, OnResizeEnd, OnResizeStart } from "@xyflow/react";
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { canvases } from "@/api/canvases";
import { AnchoredText } from "@/canvas/AnchoredText";
import { resolveText, SIZE_PX, type TextSize } from "@/canvas/colors";
import { ReviewBadge } from "@/canvas/ReviewBadge";
import { useInlineField } from "@/canvas/useInlineField";

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
  const { updateNode } = useReactFlow();
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
  // No live size mirror here. Every other element paints a box that has to
  // follow the drag; a text element's box follows the WORDS, which follow
  // the font scale below. Keeping a mirror also kept the last dragged width
  // after the drag, so the outline stayed wide around short text.
  const storedWidth = typeof d.width === "number" ? d.width : undefined;

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

  const onResizeStart: OnResizeStart = (_event, params) => {
    startRef.current = { height: params.height || 1, px: basePx };
    setLiveScale(1);
  };
  const onResize: OnResize = (_event, params) => {
    const start = startRef.current;
    if (start) setLiveScale(Math.max(0.2, params.height / start.height));
  };
  const onResizeEnd: OnResizeEnd = (_event, params) => {
    const start = startRef.current;
    startRef.current = null;
    setLiveScale(1);
    if (!start || !workspaceSlug) return;
    const next = Math.round(Math.min(200, Math.max(6, start.px * (params.height / start.height))));
    // ReactFlow keeps the size the drag ended at on the node itself, so the
    // outline stayed big even with nothing saved. Hand the box back to the
    // content: the element is as wide and as tall as the words at their new
    // size.
    updateNode(id, { width: undefined, height: undefined, style: {} });
    // Only the size of the words is written. Pinning the box would stop it
    // hugging the text: the selection outline would stay at whatever the
    // drag happened to end at, which is what made a short word sit in a
    // very wide frame.
    void canvases
      // `null` deletes the key: resizing text drops any stored box, so an
      // element that once carried a width stops wearing it and goes back to
      // hugging its words.
      .patchNode(workspaceSlug, id, { data: { font_px: next, width: null, height: null } })
      .catch(() => {
        // SSE reconciles.
      });
  };
  const fontSize = liveScale === 1 ? t.fontSize : `${Math.round(basePx * liveScale)}px`;

  return (
    <div
      className={`relative ${selected ? "cursor-move" : "cursor-pointer"}`}
      style={{
        // No border and no background: the words are the element, and the
        // box hugs them. A width is only set when someone wants a paragraph
        // to wrap at a chosen measure; otherwise the element is as wide as
        // what is written, so the selection box matches the text.
        // Height is never pinned: the words decide it. Width only when it
        // was set deliberately, to wrap a paragraph at a chosen measure.
        ...(storedWidth ? { width: storedWidth } : { width: "max-content", maxWidth: "40rem" }),
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
        // The editor is the same size as the words, so nothing moves when
        // editing starts or as you type. A textarea has an intrinsic width
        // from its `cols`, which made the element far wider than its text,
        // so a hidden copy of the value drives the box and the textarea
        // sits on top of it.
        <div style={{ display: "grid" }}>
          <div
            aria-hidden
            className="whitespace-pre-wrap break-words"
            style={{ gridArea: "1 / 1", visibility: "hidden", minWidth: "1ch" }}
          >
            {`${edit.inputProps.value}\u200b`}
          </div>
          <textarea
            {...edit.inputProps}
            // No box, no background, no outline: writing on a canvas should
            // not look like filling in a form.
            className={`${edit.inputProps.className} resize-none border-0 bg-transparent p-0 outline-none focus:outline-none`}
            style={{
              gridArea: "1 / 1",
              fontSize,
              fontFamily: t.fontFamily,
              fontWeight: t.fontWeight,
              textAlign: t.textAlign,
              color: t.color,
              lineHeight: 1.25,
              overflow: "hidden",
            }}
            placeholder="type"
          />
        </div>
      ) : (
        <div
          className="whitespace-pre-wrap break-words"
          onDoubleClick={(e) => {
            e.stopPropagation();
            edit.beginEdit();
          }}
          title={selected ? "double-click to edit" : undefined}
        >
          {text ? (
            <AnchoredText text={text} />
          ) : (
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
