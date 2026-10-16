/**
 * SectionPrimitive — a section of a document, as dragged out of it.
 *
 * A table, a block of text, a list: the page cut to the section's bbox,
 * under a small line that says what kind of section it is and which page it
 * came from. It is the section as the document shows it, not a container to
 * fill: a spec card with no rows invited the reader to retype what its own
 * picture already showed, and its search tags read as noise.
 *
 * Pictures (diagrams, drawings) stay `image` elements; this is the rest.
 */
import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useParams } from "react-router-dom";

import { ReviewBadge } from "@/canvas/ReviewBadge";
import { RoleBadge } from "@/canvas/RoleBadge";
import { SourceAnchorButton } from "@/canvas/SourceAnchorButton";
import { PictureHighlightBoxes, usePictureHighlights } from "@/canvas/PictureHighlights";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";
import { useUiStore } from "@/stores/uiStore";

import { imageSrc, type ImageSourceRef } from "./ImagePrimitive";

/** The hint over the title: "TABLE · p. 3". */
export function sectionHint(kind: unknown, page: number | undefined): string {
  const k = typeof kind === "string" && kind.trim() ? kind.trim().replace(/[_-]+/g, " ") : "section";
  return page ? `${k} · p. ${page}` : k;
}

export function SectionPrimitive({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    kind?: string;
    source_ref?: ImageSourceRef;
    source_doc_slug?: string;
    source_doc_node_id?: string;
    width?: number;
    height?: number;
  };
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const title = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: d.label ?? "",
    field: "label",
    canEdit: selected ?? false,
  });
  const { width: liveW, handlers: resizeHandlers } = useLiveResize(d.width, d.height);
  const width = liveW ?? d.width ?? 480;
  const src = imageSrc(d);
  const ref = d.source_ref;
  const refSlug = ref?.slug ?? d.source_doc_slug;
  const setHoveredSourceRef = useUiStore((s) => s.setHoveredSourceRef);
  const clearHoveredSourceRef = useUiStore((s) => s.clearHoveredSourceRef);
  const lit = usePictureHighlights(ref ? { ...ref, slug: refSlug } : null);
  return (
    <div
      data-testid="section-node"
      className={`relative rounded-lg border border-neutral-300 bg-white shadow-sm ${
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
      <NodeResizer isVisible={selected ?? false} minWidth={160} minHeight={80} color="#0ea5e9" {...resizeHandlers} />
      <Handle type="target" position={Position.Left} />
      <div className="flex items-start justify-between gap-2 border-b border-neutral-200 px-3 py-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">{sectionHint(d.kind, ref?.page)}</div>
          {title.editing ? (
            <input
              {...title.inputProps}
              className={`${title.inputProps.className} w-full rounded border border-neutral-300 px-1 py-0 text-sm font-medium outline-none focus:border-neutral-500`}
              placeholder="title"
            />
          ) : (
            <div
              className={`truncate text-sm font-medium text-neutral-900 ${selected ? "cursor-text" : ""}`}
              onDoubleClick={(e) => {
                e.stopPropagation();
                title.beginEdit();
              }}
              title={selected ? "double-click to rename" : d.label}
            >
              {(d.label ?? "").trim() || <span className="text-neutral-400">untitled section</span>}
            </div>
          )}
        </div>
        {ref && refSlug ? (
          <SourceAnchorButton
            workspaceSlug={workspaceSlug}
            documentNodeId={d.source_doc_node_id}
            refValue={{ slug: refSlug, page: ref.page, bbox: ref.bbox, region_id: ref.region_id }}
            title={`Open page ${ref.page} in viewer`}
            ariaLabel={`Open source page ${ref.page}`}
            size={12}
            className="h-6 w-6 shrink-0 border border-sky-300 bg-sky-50"
          />
        ) : null}
      </div>
      <div className="px-3 py-2">
        {src ? (
          <div className="relative">
            <img src={src} alt={d.label ?? ""} draggable={false} className="block h-auto w-full select-none" />
            <PictureHighlightBoxes boxes={lit} />
          </div>
        ) : (
          <div className="grid h-24 place-items-center rounded-sm border border-dashed border-neutral-300 text-xs text-neutral-400">
            no source yet
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
