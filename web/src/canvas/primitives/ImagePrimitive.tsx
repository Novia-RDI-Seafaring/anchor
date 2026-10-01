/**
 * ImagePrimitive — a picture on the board.
 *
 * Either a URL, or a cut from a document page: `source_ref` with a slug, a
 * page and a bbox, rendered by the server's page crop. The second is the
 * one that matters here: the dimension drawing of a pump belongs beside
 * the card that lists its dimensions, and until now nothing on the canvas
 * could show it. Cards read; this one shows.
 *
 * The caption is the node's label, editable in place when selected, the
 * way every card's heading is. The picture keeps its proportions when
 * resized; a stretched drawing is a wrong drawing.
 */
import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { documents } from "@/api/documents";
import { ReviewBadge } from "@/canvas/ReviewBadge";
import { RoleBadge } from "@/canvas/RoleBadge";
import { SourceAnchorButton } from "@/canvas/SourceAnchorButton";
import { PictureHighlightBoxes, usePictureHighlights } from "@/canvas/PictureHighlights";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";
import { useUiStore } from "@/stores/uiStore";

export type ImageSourceRef = {
  slug?: string;
  page: number;
  /** [left, top, right, bottom] in PDF points, top-left origin. */
  bbox: number[];
  region_id?: string;
};

/** Where the picture comes from, or null when the data says nothing usable. */
export function imageSrc(d: {
  src?: unknown;
  source_ref?: unknown;
  source_doc_slug?: unknown;
}): string | null {
  if (typeof d.src === "string" && d.src.trim()) return d.src;
  const ref = d.source_ref as Partial<ImageSourceRef> | undefined;
  // A section dragged from a document card carries the document's slug
  // beside the ref rather than in it.
  const slug =
    typeof ref?.slug === "string" ? ref.slug : typeof d.source_doc_slug === "string" ? d.source_doc_slug : null;
  if (ref && slug && typeof ref.page === "number" && Array.isArray(ref.bbox) && ref.bbox.length === 4) {
    return documents.pageCropUrl(slug, ref.page, ref.bbox, 200);
  }
  return null;
}

export function ImagePrimitive({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    src?: string;
    source_ref?: ImageSourceRef;
    source_doc_slug?: string;
    width?: number;
    height?: number;
  };
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const caption = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: d.label ?? "",
    field: "label",
    canEdit: selected ?? false,
  });
  const { width: liveW, handlers: resizeHandlers } = useLiveResize(d.width, d.height);
  const src = imageSrc(d);
  const width = liveW ?? d.width ?? 320;
  // Hovering the picture opens its page in the source, the way hovering a
  // row's anchor does: a picture cut from a document is a reference too.
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
  const ref = d.source_ref;
  const refSlug = ref?.slug ?? d.source_doc_slug;
  // A reference hovered elsewhere that points into this picture's page is
  // lit here too.
  const lit = usePictureHighlights(ref ? { ...ref, slug: refSlug } : null);
  return (
    <div
      data-testid="image-node"
      className={`relative rounded-md border border-neutral-200 bg-white p-1.5 shadow-sm ${
        selected ? "cursor-move" : "cursor-pointer"
      }`}
      style={{ width }}
      onMouseEnter={() => {
        if (ref && refSlug) {
          setHoveredSourceRef({ slug: refSlug, page: ref.page, region_id: ref.region_id, bbox: ref.bbox });
        }
      }}
      onMouseLeave={() => clearHoveredSourceRef()}
    >
      <ReviewBadge data={data as Record<string, unknown>} nodeId={id} />
      <RoleBadge data={data as Record<string, unknown>} />
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={120}
        minHeight={80}
        keepAspectRatio
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <Handle type="target" position={Position.Left} />
      {/* The way back to the page, as on a spec card: hover shows it, a
          click opens it. A picture cut from a document is a reference, and
          without an anchor the only route to its page was the canvas. */}
      {ref && refSlug ? (
        <SourceAnchorButton
          workspaceSlug={workspaceSlug}
          documentNodeId={(d as { source_doc_node_id?: string }).source_doc_node_id}
          refValue={{ slug: refSlug, page: ref.page, bbox: ref.bbox, region_id: ref.region_id }}
          title={`Open page ${ref.page} in viewer`}
          ariaLabel={`Open source page ${ref.page}`}
          size={12}
          className="absolute right-2 top-2 z-10 h-6 w-6 border border-sky-300 bg-sky-50/90"
        />
      ) : null}
      {src ? (
        <div className="relative">
          <img
            src={src}
            alt={d.label ?? ""}
            draggable={false}
            className="block h-auto w-full select-none rounded-sm"
          />
          <PictureHighlightBoxes boxes={lit} />
        </div>
      ) : (
        <div className="grid h-24 place-items-center rounded-sm border border-dashed border-neutral-300 text-xs text-neutral-400">
          no picture yet
        </div>
      )}
      {caption.editing ? (
        <input
          {...caption.inputProps}
          className={`${caption.inputProps.className} mt-1 w-full rounded border border-neutral-300 px-1 py-0 text-xs text-neutral-700 outline-none focus:border-neutral-500`}
          placeholder="caption"
        />
      ) : (d.label ?? "").trim() || selected ? (
        <div
          className={`mt-1 truncate text-center text-xs text-neutral-600 ${selected ? "cursor-text" : ""}`}
          onDoubleClick={(e) => {
            e.stopPropagation();
            caption.beginEdit();
          }}
          title={selected ? "double-click to edit the caption" : d.label}
        >
          {(d.label ?? "").trim() || "caption"}
        </div>
      ) : null}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
