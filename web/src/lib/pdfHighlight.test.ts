/**
 * pdfHighlight geometry tests (#110a).
 *
 * These pin the PDF-point-space -> rendered-pixel-space mapping the deep-zoom
 * bbox highlight relies on. The mapping must be order-independent in the bbox
 * tuple (Docling emits both `[l, t, r, b]` and `[l, b, r, t]`) and must honour
 * the bottom-left PDF origin (larger PDF-y maps to the top of the page).
 */
import { describe, expect, it } from "vitest";

import { bboxToViewportRect, scrollOffsetForRect } from "./pdfHighlight";

describe("bboxToViewportRect", () => {
  const pageW = 200;
  const pageH = 400;
  // Rendered at scale 2 -> 400 x 800 px.
  const viewport = { width: 400, height: 800 };

  it("maps a bbox to scaled pixel space with a top-left origin", () => {
    // bbox spans x:[50,150], PDF-y:[300,350] (near the page top).
    const rect = bboxToViewportRect([50, 300, 150, 350], pageW, pageH, viewport);
    expect(rect).not.toBeNull();
    // scale = 2 on both axes.
    expect(rect!.left).toBe(100); // 50 * 2
    expect(rect!.width).toBe(200); // (150-50) * 2
    // top = (pageH - yHigh) * sy = (400 - 350) * 2 = 100
    expect(rect!.top).toBe(100);
    expect(rect!.height).toBe(100); // (350-300) * 2
  });

  it("is order-independent in the bbox tuple", () => {
    const ltrb = bboxToViewportRect([50, 350, 150, 300], pageW, pageH, viewport);
    const lbrt = bboxToViewportRect([50, 300, 150, 350], pageW, pageH, viewport);
    expect(ltrb).toEqual(lbrt);
  });

  it("places higher PDF-y nearer the top edge (bottom-left origin)", () => {
    const high = bboxToViewportRect([10, 380, 20, 390], pageW, pageH, viewport)!;
    const low = bboxToViewportRect([10, 10, 20, 20], pageW, pageH, viewport)!;
    expect(high.top).toBeLessThan(low.top);
  });

  it("returns null for short or undefined bboxes", () => {
    expect(bboxToViewportRect(undefined, pageW, pageH, viewport)).toBeNull();
    expect(bboxToViewportRect([1, 2, 3], pageW, pageH, viewport)).toBeNull();
  });

  it("returns null for a degenerate page or viewport", () => {
    expect(bboxToViewportRect([1, 2, 3, 4], 0, pageH, viewport)).toBeNull();
    expect(bboxToViewportRect([1, 2, 3, 4], pageW, pageH, { width: 0, height: 0 })).toBeNull();
  });
});

describe("scrollOffsetForRect", () => {
  it("centres the rect in the container", () => {
    const rect = { left: 400, top: 600, width: 100, height: 100 };
    const off = scrollOffsetForRect(rect, 200, 200, 1000, 1000);
    // centre of rect = (450, 650); centre of container offset = 350, 550.
    expect(off.left).toBe(350);
    expect(off.top).toBe(550);
  });

  it("clamps to the content edges", () => {
    const rect = { left: 950, top: 950, width: 40, height: 40 };
    const off = scrollOffsetForRect(rect, 200, 200, 1000, 1000);
    expect(off.left).toBe(800); // max = 1000 - 200
    expect(off.top).toBe(800);
  });

  it("never scrolls negative", () => {
    const rect = { left: 0, top: 0, width: 10, height: 10 };
    const off = scrollOffsetForRect(rect, 200, 200, 1000, 1000);
    expect(off.left).toBe(0);
    expect(off.top).toBe(0);
  });
});
