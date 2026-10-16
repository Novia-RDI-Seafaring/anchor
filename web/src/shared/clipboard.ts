/** Clipboard gestures belong to text editors while they have focus. */
export function isTextEditing(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(
    'input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]',
  ));
}

/**
 * Cmd/Ctrl+A meant for the canvas: not in a field, and pressed on the page
 * or the canvas rather than inside a viewer, a dialog or a menu, where the
 * browser's own select-all is what the reader wants.
 */
export function isCanvasSelectAll(event: KeyboardEvent): boolean {
  if (event.defaultPrevented || event.altKey || event.shiftKey || !(event.ctrlKey || event.metaKey)) return false;
  if (event.key.toLowerCase() !== "a" || isTextEditing(event.target)) return false;
  const target = event.target;
  if (!(target instanceof Element)) return true;
  if (target === document.body || target === document.documentElement) return true;
  if (target.closest('[role="dialog"], [role="menu"], [data-testid="pdf-scroller"], aside')) return false;
  return target.closest(".react-flow, [aria-label='Canvas tools']") !== null;
}

export function clipboardKey(event: KeyboardEvent): "c" | "x" | "v" | null {
  if (event.defaultPrevented || event.altKey || !(event.ctrlKey || event.metaKey) || isTextEditing(event.target)) return null;
  const key = event.key.toLowerCase();
  return key === "c" || key === "x" || key === "v" ? key : null;
}
