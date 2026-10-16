/**
 * A value whose section is already on the canvas, and on screen, is lit there:
 * the source pane does not need to open over it.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { sectionInView } from "@/canvas/useOpenSourceRef";
import { useCanvasStore } from "@/stores/canvasStore";

function place(id: string, rect: Partial<DOMRect>) {
  const el = document.createElement("div");
  el.className = "react-flow__node";
  el.setAttribute("data-id", id);
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0,
       toJSON: () => ({}), ...rect }) as DOMRect;
  document.body.appendChild(el);
}

const ON_SCREEN = { left: 300, top: 200, right: 700, bottom: 500, width: 400, height: 300 };

beforeEach(() => {
  useCanvasStore.setState({
    nodes: {
      table: {
        id: "table", node_type: "spec",
        data: { source_doc_slug: "px", source_ref: { slug: "px", page: 3, region_id: "r3", bbox: [42, 245, 553, 388] } },
      },
      drawing: {
        id: "drawing", node_type: "image",
        data: { source_doc_slug: "px", source_ref: { slug: "px", page: 3, bbox: [45, 58, 366, 219] } },
      },
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  window.innerWidth = 1200;
  window.innerHeight = 800;
});

afterEach(() => {
  document.querySelectorAll(".react-flow__node").forEach((el) => el.remove());
});

describe("sectionInView", () => {
  it("is true for a cell of a table section on screen", () => {
    place("table", ON_SCREEN);
    expect(sectionInView({ slug: "px", page: 3, region_id: "r3" })).toBe(true);
  });

  it("is true for a box inside a picture cut on screen", () => {
    place("drawing", ON_SCREEN);
    expect(sectionInView({ slug: "px", page: 3, bbox: [292, 187, 298, 199] })).toBe(true);
  });

  it("is false when the section is off screen", () => {
    place("table", { left: -900, top: 200, right: -500, bottom: 500, width: 400, height: 300 });
    expect(sectionInView({ slug: "px", page: 3, region_id: "r3" })).toBe(false);
  });

  it("is false for a place outside every section on the canvas", () => {
    place("table", ON_SCREEN);
    place("drawing", ON_SCREEN);
    expect(sectionInView({ slug: "px", page: 2, bbox: [172, 382, 238, 408] })).toBe(false);
    expect(sectionInView({ slug: "other", page: 3, region_id: "r3" })).toBe(false);
  });
});
