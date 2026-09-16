import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { resolveText } from "@/canvas/colors";
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
  });
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );

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
        fontSize: t.fontSize,
        lineHeight: 1.25,
      }}
      data-testid="text-node"
    >
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={60}
        minHeight={24}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <ReviewBadge data={data as Record<string, unknown>} nodeId={id} />
      <Handle type="target" position={Position.Left} />
      {edit.editing ? (
        <textarea
          {...edit.inputProps}
          className={`${edit.inputProps.className} w-full resize-none rounded border border-sky-300 bg-white/90 px-1 py-0 outline-none`}
          style={{
            fontSize: t.fontSize,
            fontFamily: t.fontFamily,
            fontWeight: t.fontWeight,
            textAlign: t.textAlign,
            lineHeight: 1.25,
          }}
          placeholder="text"
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
