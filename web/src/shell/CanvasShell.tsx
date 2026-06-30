/**
 * CanvasShell — the UI layer wrapping the canvas.
 *
 * Architectural rule: this layer NEVER touches `canvas/` internals. It
 * communicates with core through the same HTTP/SSE/MCP surface that any
 * external agent uses, then the canvas re-renders via SSE-delivered events.
 *
 * Layout:
 *   - Slim left tool rail (draw.io style) pinned to the left edge, holds
 *     Shapes / Cards / a producer-add menu.
 *   - Ingested files live in the left files explorer (SourceCluster, owned
 *     by CanvasPage) — the old right-side Library drawer is retired (#220).
 *   - Right-side Properties panel (inspector) opens when a node is selected.
 *   - ActivityToast lives in the bottom-right.
 *
 * Future-proofing: an opt-in bottom-middle floating chat input has been
 * flagged. The rail pins to the left, ActivityToast sits in the bottom-right
 * — neither will fight a future bottom-centre input. Keep new floating UI
 * off the centre-bottom axis until that feature lands.
 */
import { ReactFlowProvider } from "@xyflow/react";

import { ActivityToast } from "@/canvas/ActivityToast";
import { DirectionalConnectors } from "@/canvas/DirectionalConnectors";

import { IngestActivityPill } from "./IngestActivityPill";
import { LeftToolRail } from "./LeftToolRail";
import { PropertiesPanel } from "./PropertiesPanel";

type Props = {
  workspaceSlug: string;
  children: React.ReactNode;  // the CanvasGraph
};

export function CanvasShell({ workspaceSlug, children }: Props) {
  return (
    <ReactFlowProvider>
      <div className="relative flex h-full w-full">
        <div className="relative flex-1">
          {children}
          <LeftToolRail workspaceSlug={workspaceSlug} />
          {/* Miro-style 4-dot quick-connect overlay. Sits above the
              ReactFlow viewport (CSS position: fixed) but is mounted
              inside the provider so it can read selection state +
              transform via useStore. Renders nothing when not in single-
              select mode. */}
          <DirectionalConnectors workspaceSlug={workspaceSlug} />
          {/* Project-level ingestion-activity pill (issue #51): bottom-left,
              live for every in-flight ingest regardless of trigger. */}
          <IngestActivityPill />
          <ActivityToast />
        </div>
        <PropertiesPanel />
      </div>
    </ReactFlowProvider>
  );
}
