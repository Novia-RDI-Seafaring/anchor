import { isTextEditing } from "@/shared/clipboard";

export type CanvasNavigationMode = "select" | "hand";

/** Canvas navigation does not own keys in editors, source panes or dialogs. */
export function navigationKey(event: KeyboardEvent): CanvasNavigationMode | null {
  if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || isTextEditing(event.target)) return null;
  const key = event.key.toLowerCase();
  if (key !== "v" && key !== "h") return null;
  const target = event.target;
  if (target instanceof Element) {
    if (target.closest('[data-canvas-read-only="true"], [role="dialog"], [role="menu"]')) return null;
    const rail = target.closest('[aria-label="Canvas tools"]');
    if (target !== document.body && target !== document.documentElement && !rail
      && (!target.closest(".react-flow") || target.closest('button, a, [role="button"]'))) return null;
  } else if (target instanceof Node) return null;
  return key === "h" ? "hand" : "select";
}

/**
 * What a drag on the canvas does. With no tool armed, dragging the empty
 * canvas pans and Shift-dragging draws a selection box (React Flow's
 * `selectionKeyCode`); elements are clicked and dragged as themselves. A
 * separate pointer mode for selecting asked the reader to switch modes for
 * the most common gesture. The hand is a view-only mode: everything pans and
 * nothing moves. An armed tool owns the primary button, so the canvas pans
 * with the middle or right one. Holding space is the hand for as long as it
 * is held: a drag that starts on a card pans rather than moving the card.
 */
export function canvasNavigation(
  mode: CanvasNavigationMode, readOnly: boolean, armedTool: string | null, panKeyHeld = false,
) {
  const hand = !readOnly && !armedTool && mode === "hand";
  return {
    hand,
    nodesDraggable: !readOnly && !hand && !armedTool && !panKeyHeld,
    selectionOnDrag: false,
    panOnDrag: armedTool && !readOnly ? [1, 2] : true,
  };
}

/** Per-node drag overrides must obey the tool that owns the gesture. */
export function navigationNodes<T extends { draggable?: boolean }>(
  nodes: T[], navigation: ReturnType<typeof canvasNavigation>,
): T[] {
  if (navigation.hand) {
    return nodes.map((node) => ({ ...node, selected: false, draggable: false, selectable: false, connectable: false, deletable: false }));
  }
  return navigation.nodesDraggable ? nodes : nodes.map((node) => ({ ...node, draggable: false }));
}
