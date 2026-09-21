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
  /** `transient: true` marks a hover-opened pane, which a mouse-out closes. */
  opts?: { transient?: boolean },
) => void {
  const openPdf = useUiStore((s) => s.openPdf);
  const knownNodeId = options?.documentNodeId;
  return useCallback(
    (ref, query, opts) => {
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
          transient: opts?.transient,
        });
      // Resolve when the ref names anything below the page. A cell or item
      // selector tightens the box; a region-only ref -- the common shape an
      // `anchor:` link writes -- carries no bbox at all, so without resolving
      // it the viewer opened the page and highlighted nothing (#385).
      const needsBox = !ref?.bbox && typeof ref?.region_id === "string";
      if (refHasSelector(ref) || needsBox) {
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
export function documentNodeIdFor(slug: string): string | undefined {
  const nodes = useCanvasStore.getState().nodes;
  for (const node of Object.values(nodes)) {
    if (node.node_type !== "document") continue;
    if ((node.data as { slug?: string } | undefined)?.slug === slug) return node.id;
  }
  return undefined;
}

/**
 * Is the document card for `slug` placed on this canvas AND actually on screen?
 *
 * Placement alone is not enough. A card parked off in a far corner of the board
 * can be highlighted all day and the reader will never see it, which is worse
 * than opening the pane: nothing at all appears to happen. So this asks the
 * rendered canvas, not the store -- React Flow puts the node id on the DOM
 * element, and the browser already knows where the viewport transform has put
 * it. A card mostly scrolled off one edge does not count either.
 */
export function documentCardInView(slug: string | undefined): boolean {
  if (!slug || typeof document === "undefined") return false;
  const nodeId = documentNodeIdFor(slug);
  if (!nodeId) return false;
  // Matched by attribute rather than built into a selector: node ids come from
  // the server and are not guaranteed to be selector-safe.
  const el = Array.from(document.querySelectorAll(".react-flow__node")).find(
    (n) => n.getAttribute("data-id") === nodeId,
  );
  if (!el) return false;
  const r = el.getBoundingClientRect();
  if (r.width < 40 || r.height < 40) return false;
  // Most of the card, not a sliver of its edge.
  const visibleW = Math.min(r.right, window.innerWidth) - Math.max(r.left, 0);
  const visibleH = Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0);
  if (visibleW <= 0 || visibleH <= 0) return false;
  return (visibleW * visibleH) / (r.width * r.height) >= 0.6;
}
