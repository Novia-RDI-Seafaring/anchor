/**
 * PropertiesPanel — right-side off-canvas Sheet for editing the currently
 * selected node.
 *
 * Coexistence rule (Library vs Properties):
 *   Only one right-side drawer is open at a time. When a node is selected
 *   on the canvas, the Library closes and Properties opens. When the user
 *   manually opens Library again, Properties closes. The mutual exclusion
 *   is enforced in `uiStore.setPropertiesOpen` and `setLibraryDrawerOpen`
 *   (the parallel Library agent owns the latter; we coordinated on the
 *   contract). Rationale: side-by-side drawers crowd a narrow viewport
 *   and the "open Library and select a node" gesture would otherwise be
 *   ambiguous. Letting selection win keeps the panel attached to the
 *   user's current focus.
 *
 * Architecture:
 *   - Selected node is sourced from `useCanvasStore.nodes[selectedNodeId]`
 *     so it stays live as SSE patches roll in. No local copy.
 *   - Editor dispatch lives in `PropertiesPanel.dispatch.ts` — kept pure
 *     so it's trivially unit-testable. The dispatcher returns one of the
 *     editor components from `./editors/*`.
 *   - All writes go through `canvases.patchNode` via `_usePatchNode`,
 *     which debounces 300ms. The SSE echo lands via the existing
 *     version-monotonic `applyEvent` in `canvasStore` — idempotent, so
 *     local-then-echo double-application is a non-issue.
 */
import { useEffect } from "react";
import { useParams } from "react-router-dom";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { dispatchEditor } from "./PropertiesPanel.dispatch";

export function PropertiesPanel() {
  const open = useUiStore((s) => s.propertiesOpen);
  const setPropertiesOpen = useUiStore((s) => s.setPropertiesOpen);
  const selectedNodeId = useUiStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useUiStore((s) => s.setSelectedNodeId);
  const node = useCanvasStore((s) =>
    selectedNodeId ? s.nodes[selectedNodeId] ?? null : null,
  );
  const { id: workspaceSlugFromUrl } = useParams<{ id: string }>();
  const workspaceSlug = workspaceSlugFromUrl ?? "";

  // If the selected node disappears from the store (deletion, workspace
  // switch, ...), close the panel rather than render an empty shell.
  useEffect(() => {
    if (open && selectedNodeId && !node) {
      setPropertiesOpen(false);
      setSelectedNodeId(null);
    }
  }, [open, selectedNodeId, node, setPropertiesOpen, setSelectedNodeId]);

  const Editor = node ? dispatchEditor(node.node_type) : null;

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        setPropertiesOpen(next);
        if (!next) setSelectedNodeId(null);
      }}
    >
      <SheetContent side="right" className="w-96">
        <SheetHeader>
          <SheetTitle>Properties</SheetTitle>
          <SheetDescription>
            {node
              ? <>Editing <code className="rounded bg-neutral-100 px-1 font-mono">{node.node_type}</code> · {node.id}</>
              : "Select a node on the canvas to edit it."}
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-3">
          {node && Editor ? (
            <Editor workspaceSlug={workspaceSlug} node={node} />
          ) : (
            <div className="rounded border border-dashed border-neutral-300 px-3 py-4 text-center text-[12px] text-neutral-500">
              Nothing selected.
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
