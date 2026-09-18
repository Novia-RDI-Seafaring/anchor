import { useUiStore } from "@/stores/uiStore";

/**
 * The close timer for a hover-opened source pane, shared by everything that
 * can keep it alive.
 *
 * In `viewer` hover mode the pane opens on the LEFT EDGE while the link that
 * opened it is out in the canvas. So the reader has to travel to read it, and
 * travelling means leaving the link. When the timer lived inside the link
 * component, leaving the link closed the pane before the pointer could arrive:
 * it flashed and vanished, which reads as "the viewer does not work".
 *
 * So the timer lives here, and both the link and the pane can cancel it. The
 * rule is: the pane goes away when the pointer is on neither of them.
 *
 * The delay is generous for the same reason. It is not a debounce, it is the
 * time to cross the canvas, and crossing costs more than dismissing something
 * that sits under your cursor.
 */

/** Long enough to travel from a link in the canvas to the pane on the left. */
export const TRANSIENT_CLOSE_MS = 600;

let timer: number | null = null;

export function cancelTransientClose(): void {
  if (timer !== null) {
    window.clearTimeout(timer);
    timer = null;
  }
}

/**
 * Close the pane shortly, unless something cancels first.
 *
 * Only ever closes a pane THIS hover opened. One the reader clicked open, or
 * opened some other way, is theirs to close.
 */
export function scheduleTransientClose(): void {
  cancelTransientClose();
  timer = window.setTimeout(() => {
    timer = null;
    const state = useUiStore.getState();
    if (state.hoverPreviewMode !== "viewer") return;
    if (state.pdfViewerPinned) return;
    state.closePdf();
  }, TRANSIENT_CLOSE_MS);
}
