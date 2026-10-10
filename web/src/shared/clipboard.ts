/** Clipboard gestures belong to text editors while they have focus. */
export function isTextEditing(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(
    'input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]',
  ));
}

export function clipboardKey(event: KeyboardEvent): "c" | "x" | "v" | null {
  if (event.defaultPrevented || event.altKey || !(event.ctrlKey || event.metaKey) || isTextEditing(event.target)) return null;
  const key = event.key.toLowerCase();
  return key === "c" || key === "x" || key === "v" ? key : null;
}
