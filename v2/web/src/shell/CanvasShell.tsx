/**
 * CanvasShell — the UI layer wrapping the canvas.
 *
 * Architectural rule: this layer NEVER touches `canvas/` internals. It
 * communicates with core through the same HTTP/SSE/MCP surface that any
 * external agent uses, then the canvas re-renders via SSE-delivered events.
 *
 * Slots:
 *   - LeftRail (Palette · Library)
 *   - Canvas viewport (passed as children)
 *   - PDF viewer modal (mounted at the page level, since it overlays the
 *     entire shell when open)
 */
import { ReactFlowProvider } from "@xyflow/react";

import { ActivityToast } from "@/canvas/ActivityToast";

import { LeftRail } from "./LeftRail";

type Props = {
  workspaceSlug: string;
  children: React.ReactNode;  // the CanvasGraph
};

export function CanvasShell({ workspaceSlug, children }: Props) {
  return (
    <ReactFlowProvider>
      <div className="flex h-full w-full">
        <LeftRail workspaceSlug={workspaceSlug} />
        <div className="relative flex-1">
          {children}
          <ActivityToast />
        </div>
      </div>
    </ReactFlowProvider>
  );
}
