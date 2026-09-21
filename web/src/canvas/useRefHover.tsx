import { useEffect, useRef, useState } from "react";

import type { ResolvableRef } from "@/api/documents";
import { CLOSE_DELAY_MS, OPEN_DELAY_MS, RefHoverPreview } from "@/canvas/RefHoverPreview";
import { cancelTransientClose, scheduleTransientClose } from "@/canvas/transientViewer";
import { documentCardInView, useOpenSourceRef } from "@/canvas/useOpenSourceRef";
import { useUiStore } from "@/stores/uiStore";

/**
 * useRefHover — hovering a source ref shows the source, wherever the ref is.
 *
 * The behaviour was built into `SourceRefLink`, so it only ever worked for
 * refs written inline in prose. The anchor buttons in a spec table carry the
 * same kind of ref and did nothing at all on hover, which reads as the
 * feature being broken rather than absent: two anchors on one canvas, one
 * live and one dead.
 *
 * So the timers live here and both callers share them. Which of the two
 * previews you get is the user's setting, not the call site's:
 *
 *   panel  — a crop beside the pointer, cheap and local.
 *   viewer — the full source pane fades in, marked transient so leaving
 *            takes it away and a click pins it.
 *
 * The open delay stops previews strobing as the pointer sweeps across a
 * column of anchors; the close delay lets the pointer reach the panel.
 *
 * Which of them applies is decided in this order:
 *
 *   1. The source pane is already open -> move it. The reader opened it and is
 *      looking at it, so the next ref swaps its page and the mark travels to
 *      the new box, wherever the ref points.
 *   2. The document is already on the canvas and in view -> light up the card
 *      and open nothing. That is the behaviour the canvas had before any of
 *      this existed. Covering a document the reader can already see with a
 *      second copy of it is the worst of both, and it costs them the canvas
 *      they arranged.
 *   3. Otherwise -> the panel or the pane, per the reader's setting.
 *
 * A click always opens the pane, because a click is a commitment to read --
 * and from then on rule 1 keeps every later hover in it.
 */
export function useRefHover(
  workspaceSlug: string | undefined,
  refValue: ResolvableRef | null | undefined,
  /** Text to highlight inside the region, when the caller has it. */
  query?: string,
) {
  const openRef = useOpenSourceRef(workspaceSlug);
  const hoverMode = useUiStore((s) => s.hoverPreviewMode);
  const [previewRect, setPreviewRect] = useState<DOMRect | null>(null);
  const openTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);

  const cancelTimers = () => {
    if (openTimer.current !== null) window.clearTimeout(openTimer.current);
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    openTimer.current = null;
    closeTimer.current = null;
    cancelTransientClose();
  };

  const scheduleOpen = (el: HTMLElement) => {
    cancelTimers();
    const rect = el.getBoundingClientRect();
    openTimer.current = window.setTimeout(() => {
      if (!refValue) return;
      // An open pane wins everything. Once the reader has opened it they are
      // looking at it, so the next ref moves the mark THERE -- the pane swaps
      // document and page in place and the mark travels to the new box. Showing
      // them a crop beside the link instead, or lighting up a card behind the
      // pane, answers a question they are not asking.
      //
      // `transient: true` leaves the pinned flag as it was: a pane they clicked
      // open stays open when the pointer leaves, one a hover opened still goes
      // away. Either way the mark follows the pointer.
      if (useUiStore.getState().pdfViewer) {
        openRef(refValue, query, { transient: true });
        return;
      }
      // Nothing open, but the document is already on the canvas and visible:
      // the card does the showing.
      if (documentCardInView(refValue.slug)) return;
      if (hoverMode === "viewer") {
        openRef(refValue, query, { transient: true });
      } else {
        setPreviewRect(rect);
      }
    }, OPEN_DELAY_MS);
  };

  const scheduleClose = () => {
    cancelTimers();
    closeTimer.current = window.setTimeout(() => setPreviewRect(null), CLOSE_DELAY_MS);
    // The pane's own timer is shared, because the pane sits on the far left
    // and the reader has to leave the ref to reach it. Entering the pane
    // cancels it; see transientViewer.
    if (hoverMode === "viewer") scheduleTransientClose();
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

  /**
   * Spread onto whatever element carries the ref. `data-source-trigger` marks
   * it as a thing that OPENS the pane, so the pane's click-away handler does
   * not close it in the same gesture that asked for it.
   *
   * The open hangs off the first mouse MOVE over the ref, not off `mouseenter`.
   * The two are the same thing when a reader moves onto a link, because the
   * movement that carries the pointer there is itself a `mousemove` on it. They
   * are not the same thing when the element arrives under a pointer that is
   * standing still -- which is exactly what happens as the pane fades out and
   * uncovers the link that opened it. That bare `mouseenter` used to reopen the
   * pane mid-fade, restarting the fade-in from nothing: the flicker on mouse-out,
   * and a second full round of page and region requests behind it.
   */
  const armed = useRef(false);
  const setHovered = useUiStore((s) => s.setHoveredSourceRef);
  const hoverProps = {
    "data-source-trigger": "",
    onMouseEnter: () => {
      armed.current = false;
      // Broadcast wherever the ref is carried, so a document card on the canvas
      // lights up even for anchors that never did this (a spec header, a row
      // button). Clearing is left to whoever owns the surrounding element: doing
      // it here would drop the highlight while the pointer is still inside a row.
      if (refValue?.slug) {
        setHovered({
          slug: refValue.slug,
          page: refValue.page ?? 1,
          region_id: refValue.region_id,
          bbox: refValue.bbox,
          item_id: refValue.item_id,
          cell: refValue.cell,
          query,
        });
      }
    },
    onMouseMove: (event: React.MouseEvent<HTMLElement>) => {
      if (armed.current) return;
      armed.current = true;
      scheduleOpen(event.currentTarget);
    },
    onMouseLeave: () => {
      armed.current = false;
      scheduleClose();
    },
  } as const;

  const preview =
    previewRect && refValue ? (
      <RefHoverPreview
        refValue={refValue}
        anchorRect={previewRect}
        onPointerEnter={cancelTimers}
        onPointerLeave={scheduleClose}
      />
    ) : null;

  return { hoverProps, preview, cancelTimers, scheduleClose };
}
