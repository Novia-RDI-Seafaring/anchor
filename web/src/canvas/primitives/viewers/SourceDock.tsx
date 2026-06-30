import { useCallback, useEffect, useRef, useState } from "react";

import { documents, type DocumentIndex } from "@/api/documents";
import { useUiStore } from "@/stores/uiStore";

import { PdfSourceView } from "./PdfSourceView";

/**
 * SourceDock — the left-docked split-screen source pane (#110a).
 *
 * Renders ONLY the left source pane + the draggable divider; the canvas keeps
 * filling the remaining space to the right. The dock is a single shared pane:
 * opening a different document/region swaps `pdfViewer` content in place (no
 * per-document instance). The divider drags to resize and the ratio persists
 * in the uiStore for the session. Closing the dock returns to canvas-full.
 *
 * This component renders nothing unless the shared viewer is open in "dock"
 * mode, so the legacy modal quick-look path (PageWithBboxViewer) is untouched.
 */
export function SourceDock() {
  const viewer = useUiStore((s) => s.pdfViewer);
  const ratio = useUiStore((s) => s.sourceDockRatio);
  const setRatio = useUiStore((s) => s.setSourceDockRatio);
  const setPage = useUiStore((s) => s.setPdfPage);
  const setMode = useUiStore((s) => s.setPdfViewerMode);
  const close = useUiStore((s) => s.closePdf);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [index, setIndex] = useState<DocumentIndex | null>(null);

  const slug = viewer?.slug;
  const isDock = viewer?.mode === "dock";

  useEffect(() => {
    if (!slug) {
      setIndex(null);
      return;
    }
    let cancel = false;
    documents.index(slug).then((idx) => {
      if (!cancel) setIndex(idx);
    }).catch(() => {
      if (!cancel) setIndex(null);
    });
    return () => {
      cancel = true;
    };
  }, [slug]);

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      const el = containerRef.current?.parentElement;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0) return;
      setRatio((e.clientX - rect.left) / rect.width);
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

  if (!viewer || !slug || !isDock) return null;

  const total = index?.document?.page_count ?? 0;
  const docTitle = index?.document?.title ?? slug;

  return (
    <div
      ref={containerRef}
      className="flex h-full min-h-0 shrink-0 flex-col border-r border-neutral-300 bg-white"
      style={{ width: `${ratio * 100}%` }}
      data-testid="source-dock"
    >
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
          slug={slug}
          page={viewer.page}
          total={total}
          highlightBbox={viewer.highlightBbox}
          highlightPage={viewer.highlightPage}
          title={docTitle}
          onPageChange={setPage}
          canvasSlug={viewer.workspaceSlug}
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
