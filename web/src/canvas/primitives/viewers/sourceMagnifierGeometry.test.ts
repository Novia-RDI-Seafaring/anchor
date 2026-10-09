import { describe, expect, it } from "vitest";

import type { PixelRect } from "@/lib/pdfHighlight";

import { intersectRects, placeMagnifier } from "./sourceMagnifierGeometry";

const page = { left: 0, top: 0, width: 600, height: 800 };

function expectSeparate(source: PixelRect, bounds: PixelRect, lens: PixelRect | null) {
  expect(lens).not.toBeNull();
  expect(lens!.left).toBeGreaterThanOrEqual(bounds.left);
  expect(lens!.top).toBeGreaterThanOrEqual(bounds.top);
  expect(lens!.left + lens!.width).toBeLessThanOrEqual(bounds.left + bounds.width);
  expect(lens!.top + lens!.height).toBeLessThanOrEqual(bounds.top + bounds.height);
  const overlap = intersectRects(source, lens!);
  expect(overlap.width * overlap.height).toBe(0);
}

describe("source magnifier placement", () => {
  it("places a bounded lens to the right of a small source", () => {
    const source = { left: 100, top: 200, width: 30, height: 20 };
    const lens = placeMagnifier(source, page);
    expectSeparate(source, page, lens);
    expect(lens).toEqual({ left: 142, top: 154, width: 220, height: 112 });
  });

  it("flips left at the right page edge", () => {
    const source = { left: 570, top: 200, width: 30, height: 20 };
    const lens = placeMagnifier(source, page);
    expectSeparate(source, page, lens);
    expect(lens!.left + lens!.width).toBe(558);
  });

  it("uses space below a full-width source", () => {
    const source = { left: 0, top: 10, width: 600, height: 30 };
    const lens = placeMagnifier(source, page);
    expectSeparate(source, page, lens);
    expect(lens!.top).toBe(52);
  });

  it("flips above a full-width source at the bottom", () => {
    const source = { left: 0, top: 770, width: 600, height: 30 };
    const lens = placeMagnifier(source, page);
    expectSeparate(source, page, lens);
    expect(lens!.top + lens!.height).toBe(758);
  });

  it("shrinks within a narrow viewport without covering the source", () => {
    const bounds = { left: 20, top: 10, width: 180, height: 140 };
    const source = { left: 30, top: 30, width: 20, height: 20 };
    const lens = placeMagnifier(source, bounds);
    expectSeparate(source, bounds, lens);
    expect(lens!.width).toBe(138);
  });

  it("can use the visible gutter when the source fills its page", () => {
    const source = { left: 100, top: 100, width: 300, height: 300 };
    expect(placeMagnifier(source, source)).toBeNull();
    const visible = { left: 0, top: 0, width: 650, height: 500 };
    const lens = placeMagnifier(source, visible);
    expectSeparate(source, visible, lens);
    expect(lens!.left).toBe(412);
  });

  it("omits the lens when no readable non-overlapping space remains", () => {
    expect(placeMagnifier(page, page)).toBeNull();
    expect(placeMagnifier({ left: 0, top: 0, width: 20, height: 20 },
      { left: 0, top: 0, width: 70, height: 50 })).toBeNull();
    expect(placeMagnifier({ ...page, left: NaN }, page)).toBeNull();
    expect(placeMagnifier({ ...page, width: 0 }, page)).toBeNull();
  });

  it("intersects page and viewport bounds without negative dimensions", () => {
    expect(intersectRects(page, { left: -20, top: 750, width: 200, height: 100 }))
      .toEqual({ left: 0, top: 750, width: 180, height: 50 });
    expect(intersectRects(page, { left: 700, top: 900, width: 20, height: 20 }))
      .toEqual({ left: 700, top: 900, width: 0, height: 0 });
  });
});
