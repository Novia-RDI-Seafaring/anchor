import { Anchor } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ResolvableRef } from "@/api/documents";
import { describeRef } from "@/canvas/anchorHref";
import { CLOSE_DELAY_MS, OPEN_DELAY_MS, RefHoverPreview } from "@/canvas/RefHoverPreview";
import { useOpenSourceRef } from "@/canvas/useOpenSourceRef";
import { useUiStore } from "@/stores/uiStore";

/**
 * SourceRefLink — the words, then the anchor.
 *
 * An `anchor:` link inside prose renders as the text it wrapped with a
 * small anchor glyph after it. Clicking opens the document at that page
 * and highlights the region, the same landing a spec row gives you.
 * Hovering broadcasts the ref, so a document card already on the canvas
 * lights up the region under the cursor without anything being clicked.
 *
 * A ref that names no document or no page renders struck through, in the
 * colour of a problem, and says so on hover. A pointer that goes nowhere
 * is a mistake worth seeing rather than prose that quietly reads as if
 * it were sourced.
 */
export function SourceRefLink({
  workspaceSlug,
  refValue,
  children,
}: {
  workspaceSlug: string | undefined;
  /** Parsed ref, or `null` when the `anchor:` target was malformed. */
  refValue: ResolvableRef | null;
  children?: React.ReactNode;
}) {
  const openRef = useOpenSourceRef(workspaceSlug);
  const setHovered = useUiStore((s) => s.setHoveredSourceRef);
  const clearHovered = useUiStore((s) => s.clearHoveredSourceRef);
  const hoverMode = useUiStore((s) => s.hoverPreviewMode);
  const closePdf = useUiStore((s) => s.closePdf);
  const pinViewer = useUiStore((s) => s.pinPdfViewer);

  // Hover preview (#373). The open delay stops panels strobing as the cursor
  // sweeps a paragraph; the close delay lets the pointer travel from the link
  // onto the panel without it vanishing underneath.
  const [previewRect, setPreviewRect] = useState<DOMRect | null>(null);
  const openTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);

  const cancelTimers = () => {
    if (openTimer.current !== null) window.clearTimeout(openTimer.current);
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    openTimer.current = null;
    closeTimer.current = null;
  };
  const scheduleOpen = (el: HTMLElement) => {
    cancelTimers();
    openTimer.current = window.setTimeout(() => {
      if (hoverMode === "viewer") {
        // Fade the real pane in instead of a crop beside the link. Marked
        // transient so leaving takes it away again; clicking pins it.
        openRef(refValue, text, { transient: true });
      } else {
        setPreviewRect(el.getBoundingClientRect());
      }
    }, OPEN_DELAY_MS);
  };
  const scheduleClose = () => {
    cancelTimers();
    closeTimer.current = window.setTimeout(() => {
      setPreviewRect(null);
      // Only a viewer this hover opened goes away again. One the user clicked
      // open, or opened some other way, is theirs to close.
      if (hoverMode === "viewer" && !useUiStore.getState().pdfViewerPinned) {
        closePdf();
      }
    }, CLOSE_DELAY_MS);
  };

  // Never leave a panel behind: unmount, scroll and Escape all dismiss it.
  useEffect(() => cancelTimers, []);
  useEffect(() => {
    if (!previewRect) return;
    const dismiss = () => {
      cancelTimers();
      setPreviewRect(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [previewRect]);

  if (!refValue) {
    return (
      <span
        className="cursor-help text-rose-600 line-through decoration-rose-300"
        title="This source link names no document or no page, so it points nowhere."
        data-testid="source-ref-broken"
      >
        {children}
      </span>
    );
  }

  const text = typeof children === "string" ? children : undefined;
  return (
    <button
      type="button"
      className="nodrag inline items-baseline rounded-sm text-sky-700 underline decoration-sky-300 underline-offset-2 hover:decoration-sky-600"
      title={`Open ${describeRef(refValue)}`}
      data-testid="source-ref-link"
      onClick={(event) => {
        event.stopPropagation();
        cancelTimers();
        openRef(refValue, text);
        // A click is a commitment: the pane stays when the pointer leaves.
        pinViewer();
      }}
      onMouseEnter={(event) => {
        setHovered({
          slug: refValue.slug ?? "",
          page: refValue.page ?? 1,
          region_id: refValue.region_id,
          bbox: refValue.bbox,
          item_id: refValue.item_id,
          cell: refValue.cell,
        });
        scheduleOpen(event.currentTarget);
      }}
      onMouseLeave={() => {
        clearHovered();
        scheduleClose();
      }}
    >
      {children}
      <Anchor
        className="ml-0.5 inline size-[0.85em] -translate-y-[0.05em] stroke-sky-500"
        aria-label="source"
      />
      {previewRect ? (
        <RefHoverPreview
          refValue={refValue}
          anchorRect={previewRect}
          onPointerEnter={cancelTimers}
          onPointerLeave={scheduleClose}
        />
      ) : null}
    </button>
  );
}
