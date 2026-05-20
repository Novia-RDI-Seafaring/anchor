/**
 * LibraryDrawer — right-side off-canvas sheet wrapping the Library list.
 *
 * Open trigger: the Library button on the floating Toolbar, or the `]`
 * keyboard shortcut. Closes on Esc, click-outside, or the X button (all
 * provided by the shadcn Sheet primitive). Drag behaviour is unchanged
 * from the old LeftRail Library tab — items still emit the same
 * `application/x-anchor-node` payload, and the canvas's drop handler
 * doesn't need to know whether the drag started from a drawer or a rail.
 */
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useUiStore } from "@/stores/uiStore";

import { Library } from "./Library";

type Props = { workspaceSlug: string };

export function LibraryDrawer({ workspaceSlug }: Props) {
  const open = useUiStore((s) => s.libraryDrawerOpen);
  const setOpen = useUiStore((s) => s.setLibraryDrawerOpen);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="right" className="w-96">
        <SheetHeader>
          <SheetTitle>Library</SheetTitle>
          <SheetDescription>
            Drag any item onto the canvas to add it as a node.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-3">
          <Library workspaceSlug={workspaceSlug} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
