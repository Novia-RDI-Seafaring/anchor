/**
 * useOpenSourceRef — open the document a `source_ref` points at.
 *
 * The behaviour a spec row already has: ask the backend resolver for the
 * tightest stored box (cell > item > region > bbox), open the document
 * there, highlight it. Lifted out of the spec table so prose can do the
 * same thing, because a ref written inline in a Markdown card and a ref
 * attached to a table row mean the same and should land in the same place.
 *
 * The document node id is looked up from the canvas by slug when the
 * caller doesn't already know it, so the viewer opens beside the right
 * card on the canvas.
 */
import { useCallback } from "react";

import { documents, refHasSelector, type ResolvableRef } from "@/api/documents";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

export function useOpenSourceRef(
  workspaceSlug: string | undefined,
  options?: {
    /** The document card this ref belongs to, when the caller knows it. */
    documentNodeId?: string;
  },
): (
  ref: ResolvableRef | null | undefined,
  /** Text to highlight inside the region, when the caller has it. */
  query?: string,
) => void {
  const openPdf = useUiStore((s) => s.openPdf);
  const knownNodeId = options?.documentNodeId;
  return useCallback(
    (ref, query) => {
      const slug = ref?.slug;
      if (!slug || !ref?.page) return;
      const open = (page: number, bbox?: number[]) =>
        openPdf(slug, {
          page,
          workspaceSlug,
          documentNodeId: knownNodeId ?? documentNodeIdFor(slug),
          highlightRegionId: ref.region_id,
          highlightBbox: bbox,
          highlightQuery: query,
        });
      if (refHasSelector(ref)) {
        const fallbackPage = ref.page;
        void documents
          .resolveRef(slug, ref)
          .then((resolved) => open(resolved?.page ?? fallbackPage, resolved?.bbox ?? ref.bbox));
        return;
      }
      open(ref.page, ref.bbox);
    },
    [openPdf, workspaceSlug, knownNodeId],
  );
}

/** The document node on this canvas that shows `slug`, if one is placed. */
function documentNodeIdFor(slug: string): string | undefined {
  const nodes = useCanvasStore.getState().nodes;
  for (const node of Object.values(nodes)) {
    if (node.node_type !== "document") continue;
    if ((node.data as { slug?: string } | undefined)?.slug === slug) return node.id;
  }
  return undefined;
}
