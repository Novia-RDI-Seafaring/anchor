/**
 * The wheel, when the pointer is on a source reference out in the canvas.
 * A reader hovering a link is looking at the pane, so that is what should
 * zoom — not the board underneath the pointer.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { onViewerZoomRequest, requestViewerZoom, viewerAcceptsZoom } from "@/canvas/viewerZoom";

afterEach(() => {
  // Leave no listener behind for the next test.
  onViewerZoomRequest(() => {})();
});

describe("viewerZoom", () => {
  it("says nothing is listening until a pane opens", () => {
    expect(viewerAcceptsZoom()).toBe(false);
  });

  it("carries the gesture to the open pane", () => {
    const seen: [number, number][] = [];
    onViewerZoomRequest((d, m) => seen.push([d, m]));
    expect(viewerAcceptsZoom()).toBe(true);
    requestViewerZoom(-120, 0);
    expect(seen).toEqual([[-120, 0]]);
  });

  it("drops the gesture once the pane has gone", () => {
    const seen: number[] = [];
    const stop = onViewerZoomRequest((d) => seen.push(d));
    stop();
    requestViewerZoom(-120);
    expect(seen).toEqual([]);
    expect(viewerAcceptsZoom()).toBe(false);
  });

  it("does not throw when nobody is listening", () => {
    expect(() => requestViewerZoom(-120)).not.toThrow();
  });

  it("gives the newest pane the gesture, not the one it replaced", () => {
    // One shared pane: opening a second document swaps content in place, and
    // a stale subscriber would steer a reader that is no longer there.
    const first: number[] = [];
    const second: number[] = [];
    onViewerZoomRequest((d) => first.push(d));
    onViewerZoomRequest((d) => second.push(d));
    requestViewerZoom(-120);
    expect(first).toEqual([]);
    expect(second).toEqual([-120]);
  });

  it("a stale unsubscribe does not silence the pane that replaced it", () => {
    const first: number[] = [];
    const second: number[] = [];
    const stopFirst = onViewerZoomRequest((d) => first.push(d));
    onViewerZoomRequest((d) => second.push(d));
    stopFirst();
    requestViewerZoom(-120);
    expect(second).toEqual([-120]);
  });

  it("passes the wheel's delta mode through, so a line-mode wheel is not read as pixels", () => {
    const modes: number[] = [];
    onViewerZoomRequest((_d, m) => modes.push(m));
    requestViewerZoom(-3, 1);
    expect(modes).toEqual([1]);
  });
});
