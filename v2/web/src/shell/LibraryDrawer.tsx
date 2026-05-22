/**
 * LibraryDrawer — right-side off-canvas sheet wrapping two peer browsers:
 *
 *   - **Documents** (default): ingested PDFs + CAD models. Drag a row onto
 *     the canvas to instantiate a new node from that artefact.
 *   - **Canvases**: all workspaces. Drag a row onto the canvas to attach
 *     it as a linked sub-canvas tile (`data.canvas_slug` points at the
 *     dragged workspace). Does NOT create a child — that's the rail's
 *     `+ Sub-canvas` job.
 *
 * Open trigger: the Library button on the floating Toolbar, or the `]`
 * keyboard shortcut. Closes on Esc, click-outside, or the X button (all
 * provided by the shadcn Sheet primitive). Drag behaviour from the
 * Documents tab is unchanged from the old LeftRail Library tab — items
 * still emit the same `application/x-anchor-node` payload. The Canvases
 * tab emits the new `application/x-anchor-canvas-link` mime; the canvas's
 * drop handler dispatches on the mime type.
 */
import { useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useUiStore } from "@/stores/uiStore";

import { CanvasesPanel } from "./CanvasesPanel";
import { Library } from "./Library";

type Props = { workspaceSlug: string };

type TabKey = "documents" | "canvases";

export function LibraryDrawer({ workspaceSlug }: Props) {
  const open = useUiStore((s) => s.libraryDrawerOpen);
  const setOpen = useUiStore((s) => s.setLibraryDrawerOpen);
  const [tab, setTab] = useState<TabKey>("documents");

  // `modal={false}` is critical for drag-from-library → drop-on-canvas:
  // Radix Dialog's default modal overlay sits z-40 over the canvas and
  // catches pointer events, so a drop from inside the drawer lands on
  // the overlay (canvas onDrop never fires). Non-modal mode lets pointer
  // events pass through to the canvas while Radix still closes the
  // drawer on outside-click via `onInteractOutside` on the content.
  return (
    <Sheet open={open} onOpenChange={setOpen} modal={false}>
      <SheetContent side="right" className="w-96 pointer-events-auto">
        <SheetHeader>
          <SheetTitle>Library</SheetTitle>
          <SheetDescription>
            Drag any item onto the canvas to add it as a node.
          </SheetDescription>
          <Tabs
            value={tab}
            onValueChange={(v) => setTab(v as TabKey)}
            className="mt-2"
          >
            <TabsList>
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="canvases">Canvases</TabsTrigger>
            </TabsList>
          </Tabs>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-3">
          {tab === "documents" ? (
            <Library workspaceSlug={workspaceSlug} />
          ) : (
            <CanvasesPanel workspaceSlug={workspaceSlug} />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
