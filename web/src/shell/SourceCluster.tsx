/**
 * SourceCluster — the left source region of the canvas page (#220 part B).
 *
 * Left-to-right the page reads: `[files explorer] [PDF viewer] [CANVAS]
 * [inspector]`. This component owns the first two: the files explorer and the
 * shared PDF viewer (SourceDock). It is:
 *
 *   - **Resizable**: a vertical divider sets the explorer width; SourceDock
 *     keeps its own divider for the viewer width (ratio of the area right of
 *     the explorer). Both widths persist in uiStore.
 *   - **Collapsible**: a chevron collapses the whole cluster so the canvas
 *     spans full width. When collapsed a slim rail with an expand button
 *     stays pinned to the left so the cluster is one click from returning.
 *
 * The PDF viewer pane (SourceDock) renders itself only when a document is
 * open; otherwise just the explorer shows. Closing the viewer leaves the
 * explorer in place — files are always browsable from the left.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { SourceDock } from "@/canvas/primitives/viewers/SourceDock";
import { useUiStore } from "@/stores/uiStore";

import { FilesExplorer } from "./FilesExplorer";

type Props = { workspaceSlug: string };

export function SourceCluster({ workspaceSlug }: Props) {
  const collapsed = useUiStore((s) => s.sourceClusterCollapsed);
  const toggleCluster = useUiStore((s) => s.toggleSourceCluster);
  const explorerWidth = useUiStore((s) => s.explorerWidth);
  const setExplorerWidth = useUiStore((s) => s.setExplorerWidth);

  const clusterRef = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      const el = clusterRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setExplorerWidth(e.clientX - rect.left);
    },
    [setExplorerWidth],
  );

  const stopDrag = useCallback(() => setDragging(false), []);

  useEffect(() => {
    if (!dragging) return;
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopDrag);
    const prevSelect = document.body.style.userSelect;
    const prevCursor = document.body.style.cursor;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopDrag);
      document.body.style.userSelect = prevSelect;
      document.body.style.cursor = prevCursor;
    };
  }, [dragging, onPointerMove, stopDrag]);

  if (collapsed) {
    // Slim re-open rail so the cluster is one click away from returning.
    return (
      <div className="flex h-full shrink-0 flex-col items-center border-r border-neutral-200 bg-neutral-50 py-2">
        <button
          type="button"
          onClick={toggleCluster}
          aria-label="Expand source panel"
          title="Expand files + viewer"
          className="flex h-8 w-8 items-center justify-center rounded text-neutral-600 hover:bg-neutral-200"
          data-testid="source-cluster-expand"
        >
          »
        </button>
      </div>
    );
  }

  return (
    <div
      ref={clusterRef}
      className="flex h-full min-h-0 shrink-0"
      data-testid="source-cluster"
    >
      {/* Files explorer — fixed (resizable) width. */}
      <div
        className="relative flex h-full min-h-0 shrink-0 flex-col border-r border-neutral-200"
        style={{ width: `${explorerWidth}px` }}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-600">
          <span>Explorer</span>
          <button
            type="button"
            onClick={toggleCluster}
            aria-label="Collapse source panel"
            title="Collapse files + viewer"
            className="rounded px-1 text-neutral-500 hover:bg-neutral-200"
            data-testid="source-cluster-collapse"
          >
            «
          </button>
        </div>
        <div className="min-h-0 flex-1">
          <FilesExplorer workspaceSlug={workspaceSlug} />
        </div>

        {/* Divider to resize the explorer. */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize files explorer"
          className="absolute -right-1.5 top-0 z-10 h-full w-3 cursor-col-resize"
          onPointerDown={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          data-testid="explorer-divider"
        >
          <div className="mx-auto h-full w-px bg-neutral-200" />
        </div>
      </div>

      {/* PDF viewer pane — SourceDock renders only when a doc is open. It owns
          its own width and resize divider (ratio of the cluster width). */}
      <SourceDock />
    </div>
  );
}
