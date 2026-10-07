/**
 * SourceCluster — the files explorer down the left of the canvas page (#220).
 *
 * Left-to-right the page reads: `[files explorer] [CANVAS] [inspector]`. The
 * PDF viewer is no longer part of this row: it slides in as an overlay
 * (SourceDock, mounted by CanvasShell) so that opening a document does not
 * reflow the canvas and does not have to share the row's width with the
 * explorer. The explorer stays browsable underneath, and the viewer can cover
 * it when the pages need the room.
 *
 * Resizable via a vertical divider; collapsible to a slim rail so the canvas
 * spans full width. Both bits of state persist in uiStore.
 */
import { useCallback, useEffect, useRef, useState } from "react";

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

    </div>
  );
}
