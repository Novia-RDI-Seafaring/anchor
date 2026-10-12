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

export function canvasNavigation(mode: CanvasNavigationMode, readOnly: boolean, armedTool: string | null) {
  const hand = !readOnly && !armedTool && mode === "hand";
  return {
    hand,
    selectionOnDrag: !readOnly && !armedTool && !hand,
    panOnDrag: readOnly || hand ? true : [1, 2],
  };
}
