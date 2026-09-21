/**
 * Whether the canvas is already showing this document. Placement alone is not
 * enough: a card parked in a far corner can be highlighted all day and the
 * reader never sees it, which is worse than opening the pane, because nothing
 * appears to happen at all.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { documentCardInView } from "@/canvas/useOpenSourceRef";
import { useCanvasStore } from "@/stores/canvasStore";

const NODE_ID = "doc-card-1";

function placeCard(rect: Partial<DOMRect>) {
  const el = document.createElement("div");
  el.className = "react-flow__node";
  el.setAttribute("data-id", NODE_ID);
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0,
       toJSON: () => ({}), ...rect }) as DOMRect;
  document.body.appendChild(el);
  return el;
}

beforeEach(() => {
  useCanvasStore.setState({
    nodes: { [NODE_ID]: { id: NODE_ID, node_type: "document", data: { slug: "lkh" } } },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  window.innerWidth = 1200;
  window.innerHeight = 800;
});

afterEach(() => {
  document.querySelectorAll(".react-flow__node").forEach((el) => el.remove());
});

describe("documentCardInView", () => {
  it("is true for a card sitting in the middle of the screen", () => {
    placeCard({ left: 300, top: 200, right: 700, bottom: 500, width: 400, height: 300 });
    expect(documentCardInView("lkh")).toBe(true);
  });

  it("is false when no card for that document is placed", () => {
    placeCard({ left: 300, top: 200, right: 700, bottom: 500, width: 400, height: 300 });
    expect(documentCardInView("some-other-doc")).toBe(false);
  });

  it("is false when the card is scrolled off the canvas entirely", () => {
    placeCard({ left: -900, top: 200, right: -500, bottom: 500, width: 400, height: 300 });
    expect(documentCardInView("lkh")).toBe(false);
  });

  it("is false when only a sliver of the card is showing", () => {
    // Hanging off the right edge with 40px of 400 visible: highlighting it
    // would put the mark somewhere the reader cannot see.
    placeCard({ left: 1160, top: 200, right: 1560, bottom: 500, width: 400, height: 300 });
    expect(documentCardInView("lkh")).toBe(false);
  });

  it("is false for a card zoomed down to a speck", () => {
    placeCard({ left: 300, top: 200, right: 320, bottom: 215, width: 20, height: 15 });
    expect(documentCardInView("lkh")).toBe(false);
  });

  it("is false for no slug at all", () => {
    expect(documentCardInView(undefined)).toBe(false);
  });
});
