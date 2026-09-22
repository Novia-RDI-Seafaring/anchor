/**
 * The wheel, when the pointer is on a source reference out in the canvas.
 *
 * A reader hovering a link is looking at the pane, not at the link. So the
 * wheel should drive the pane. Without this it drives whatever is under the
 * pointer, which is the canvas: the board zooms, the thing they are reading
 * does not, and they have to travel across the screen to adjust it.
 *
 * The pane's zoom is local state inside the reader, not something the canvas
 * can reach, so the request travels through here rather than through the
 * store. It is a passing gesture, not a piece of state anything needs to read
 * back, and putting it in the store would mean every subscriber re-rendering
 * on every wheel notch.
 *
 * Deliberately NOT automatic. An earlier attempt zoomed to each reference on
 * its own judgement, and it was wrong often enough to be worse than nothing:
 * the reader had set a zoom for a reason, and the viewer kept overruling it.
 * Here the reader asks, so there is nothing to get wrong.
 */

type Listener = (deltaY: number, deltaMode: number) => void;

let listener: Listener | null = null;

/** The open pane registers to receive wheel gestures made elsewhere. */
export function onViewerZoomRequest(fn: Listener): () => void {
  listener = fn;
  return () => {
    if (listener === fn) listener = null;
  };
}

/** True when a pane is listening, so a caller knows to claim the gesture. */
export function viewerAcceptsZoom(): boolean {
  return listener !== null;
}

/** Ask the open pane to zoom, as one wheel notch would. */
export function requestViewerZoom(deltaY: number, deltaMode = 0): void {
  listener?.(deltaY, deltaMode);
}
