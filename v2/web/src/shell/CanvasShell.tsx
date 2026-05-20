/**
 * CanvasShell — the UI layer wrapping the canvas.
 *
 * Architectural rule: this layer NEVER touches `canvas/` internals. It
 * communicates with core through the same HTTP/SSE/MCP surface that any
 * external agent uses, then the canvas re-renders via SSE-delivered events.
 *
 * Layout (post-refactor):
 *   - No permanent side rail. The canvas fills the viewport.
 *   - Floating top toolbar (centred under the page header) with Shapes /
 *     Cards / Producers sections, drag-out same as before.
 *   - Right-side Library drawer (shadcn Sheet) opens from the Library
 *     button on the toolbar or via the `]` shortcut.
 *   - ActivityToast lives in the bottom-right so it doesn't fight the
 *     toolbar for the top edge.
 *
 * Future-proofing: a future opt-in bottom-middle floating chat input has
 * been flagged. The toolbar pins to the top, the drawer slides in from
 * the right, ActivityToast sits in the bottom-right — none of those will
 * fight a future bottom-centre input. Keep new floating UI off the
 * centre-bottom axis until that feature lands.
 */
import { ReactFlowProvider } from "@xyflow/react";

import { ActivityToast } from "@/canvas/ActivityToast";

import { LibraryDrawer } from "./LibraryDrawer";
import { PropertiesPanel } from "./PropertiesPanel";
import { Toolbar } from "./Toolbar";

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
          {/* Floating top toolbar — centred. `pointer-events-none` on the
              wrapper lets canvas drags pass through the empty regions on
              either side of the pill; the pill itself re-enables pointer
              events. */}
          <div className="pointer-events-none absolute inset-x-0 top-3 z-20 flex justify-center">
            <Toolbar workspaceSlug={workspaceSlug} />
          </div>
          <ActivityToast />
        </div>
        <LibraryDrawer workspaceSlug={workspaceSlug} />
        <PropertiesPanel />
      </div>
    </ReactFlowProvider>
  );
}
