import { useCallback, useEffect, useRef, useState } from "react";

import { useDocumentIndex } from "@/api/useDocumentIndex";
import { cancelTransientClose, scheduleTransientClose } from "@/canvas/transientViewer";
import { useUiStore } from "@/stores/uiStore";

import { PdfSourceView } from "./PdfSourceView";

/**
 * SourceDock — the source pane that slides in over the page (#110a).
 *
 * It used to be an in-flow flex sibling between the files explorer and the
 * canvas, so opening it squeezed BOTH: the canvas reflowed and the PDF got
 * whatever was left between the explorer and the board. On a laptop that left
 * the pages too narrow to read, which is the whole point of opening them.
 *
 * Now it is an overlay anchored to the left edge of the page. It takes its
 * width from the viewport rather than from the space left over, so it can
 * cover the explorer and give the pages room, and the canvas underneath never
 * reflows -- nothing moves when the viewer opens or closes, which also means
 * no re-layout cost on every open.
 *
 * Still a single shared pane: opening a different document or region swaps
 * `pdfViewer` content in place. The divider drags to resize, the ratio
 * persists in uiStore, and Escape closes.
 *
 * Renders nothing unless the shared viewer is open in "dock" mode, so the
 * full-screen quick-look path (PageWithBboxViewer) is untouched.
 */
/** Keep in step with `.anchor-source-out` in index.css. */
const FADE_OUT_MS = 120;

export function SourceDock() {
  const viewer = useUiStore((s) => s.pdfViewer);
  const ratio = useUiStore((s) => s.sourceDockRatio);
  const setRatio = useUiStore((s) => s.setSourceDockRatio);
  const setPage = useUiStore((s) => s.setPdfPage);
  const setMode = useUiStore((s) => s.setPdfViewerMode);
  const close = useUiStore((s) => s.closePdf);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);

  const slug = viewer?.slug;
  const isDock = viewer?.mode === "dock";
  const index = useDocumentIndex(slug, isDock);
  const generation = index?.document.generation?.id;

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      // The overlay is anchored to the left edge of the window, so the drag
      // maps straight onto the viewport. (It used to measure the parent flex
      // row, which no longer describes where the pane sits.)
      const width = window.innerWidth;
      if (width <= 0) return;
      setRatio(e.clientX / width);
    },
    [setRatio],
  );

  const stopDrag = useCallback(() => {
    setDragging(false);
  }, []);

  useEffect(() => {
    if (!dragging) return;
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopDrag);
    // Avoid text selection / iframe capture while dragging.
    const prev = document.body.style.userSelect;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopDrag);
      document.body.style.userSelect = prev;
      document.body.style.cursor = "";
    };
  }, [dragging, onPointerMove, stopDrag]);

  // Exit animation bookkeeping. `exiting` keeps the pane rendered for the
  // length of the fade after the viewer state clears.
  const lastShown = useRef<{ viewer: NonNullable<typeof viewer>; slug: string } | null>(null);
  const [exiting, setExiting] = useState(false);
  const wasOpen = useRef(false);
  useEffect(() => {
    const isOpen = Boolean(viewer && slug && isDock);
    if (isOpen) {
      // Reopened (or opened at a different ref): cancel any pending fade.
      wasOpen.current = true;
      setExiting(false);
      return undefined;
    }
    if (!wasOpen.current) return undefined;
    wasOpen.current = false;
    setExiting(true);
    const id = window.setTimeout(() => setExiting(false), FADE_OUT_MS);
    return () => window.clearTimeout(id);
    // `exiting` is deliberately NOT a dependency: including it re-ran this
    // effect the instant it was set, and the cleanup then cancelled the very
    // timer that ends the fade, so the pane never unmounted.
  }, [viewer, slug, isDock]);

  // Escape closes the dock — but let the floating "Make reference" menu (and an
  // active text selection) consume the first Escape, so it takes two presses to
  // go from "menu open" to "viewer closed" rather than closing everything at once.
  useEffect(() => {
    if (!isDock) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (document.querySelector('[data-testid="make-reference-action"]')) return;
      const sel = window.getSelection();
      if (sel && !sel.isCollapsed) return;
      close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isDock, close]);

  // Keep the pane mounted through its fade-out. React unmounts the moment the
  // viewer state clears, which gives an instant disappearance -- fine for a
  // click-to-close, jarring when a pointer drifting off a link takes half the
  // screen with it. Hold the last payload for the length of the fade.
  const open = Boolean(viewer && slug && isDock);
  if (open) lastShown.current = { viewer: viewer!, slug: slug! };
  const shown = lastShown.current;
  if (!shown || (!open && !exiting)) return null;

  const { viewer: shownViewer, slug: shownSlug } = shown;
  const total = index?.document?.page_count ?? 0;
  const docTitle = index?.document?.title ?? shownSlug;

  return (
    <div
      ref={containerRef}
      // Opacity only, in and out. Sliding would drag the PAGES across the
      // screen, and a reader watching a page travel is reading nothing.
      className={`${exiting ? "anchor-source-out" : "anchor-source-in"} fixed inset-y-0 left-0 z-30 flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-neutral-300 bg-white shadow-2xl`}
      // Width is a fraction of the VIEWPORT, not of the space left over beside
      // the explorer, so the pages get real room and the pane can cover the
      // explorer. min/max keep it usable and keep some canvas reachable.
      style={{
        width: `calc(${ratio} * 100vw)`,
        minWidth: "20rem",
        maxWidth: "85vw",
      }}
      data-testid="source-dock"
      // A hover-opened pane must survive the trip to it. Arriving cancels the
      // pending close; leaving starts it again.
      onPointerEnter={cancelTransientClose}
      onPointerLeave={scheduleTransientClose}
    >
      {/* References now live inside the viewer's left rail as a tab next to
          Pages (see PdfSourceView), so a long citation can't stretch the dock. */}
      <div className="flex items-center justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1 text-xs text-neutral-600">
        <span className="font-medium uppercase tracking-wide">Source</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setMode("modal")}
            className="rounded px-1.5 py-0.5 hover:bg-neutral-200"
            title="Open as full-screen quick-look"
          >
            ⤢ Full screen
          </button>
          <button
            type="button"
            onClick={close}
            className="rounded px-1.5 py-0.5 hover:bg-neutral-200"
            title="Close source pane"
            aria-label="Close source pane"
          >
            ✕
          </button>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <PdfSourceView
          key={`${shownSlug}:${generation ?? "legacy"}`}
          slug={shownSlug}
          generation={generation}
          page={Math.min(shownViewer.page, total || 1)}
          total={total}
          highlightBbox={shownViewer.highlightBbox}
          highlightPage={shownViewer.highlightPage}
          highlightNonce={shownViewer.nonce}
          title={docTitle}
          onPageChange={setPage}
          canvasSlug={shownViewer.workspaceSlug}
        />
        {/* Draggable divider, pinned to the dock's right edge. */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize source pane"
          className="absolute -right-1.5 top-0 z-10 h-full w-3 cursor-col-resize"
          onPointerDown={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          data-testid="source-dock-divider"
        >
          <div className="mx-auto h-full w-px bg-neutral-300" />
        </div>
      </div>
    </div>
  );
}
