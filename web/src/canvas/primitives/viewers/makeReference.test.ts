/**
 * Selection -> source_ref mapping tests (#110b).
 *
 * Pins the contract the "Make reference" action relies on:
 *   - text selection -> source_ref carries the exact quote + page + a bbox in
 *     PDF points (round-trips through the rendered-pixel <-> PDF-points map),
 *   - a selection overlapping a gold region also stamps region_id,
 *   - region selection -> source_ref carries the region bbox + region_id,
 *   - the pixel<->points geometry inverts the deep-zoom highlight mapping.
 */
import { describe, expect, it } from "vitest";

import { bboxToViewportRect } from "@/lib/pdfHighlight";
import type { Region } from "@/api/documents";

import {
  bboxesOverlap,
  buildRegionSourceRef,
  buildTextSourceRef,
  defaultReferenceLabel,
  findOverlappingRegion,
  unionRectsRelativeTo,
  viewportRectToBbox,
} from "./makeReference";

const PAGE_W = 612; // US Letter points
const PAGE_H = 792;
const VIEW_W = 612; // rendered at scale 1 for simple arithmetic
const VIEW_H = 792;

describe("unionRectsRelativeTo", () => {
  it("unions client rects into one page-relative rect", () => {
    const origin = { left: 100, top: 50 };
    const rect = unionRectsRelativeTo(
      [
        { left: 120, top: 60, right: 200, bottom: 80 },
        { left: 130, top: 80, right: 260, bottom: 100 },
      ],
      origin,
    );
    // union: left 120..260 -> width 140; top 60..100 -> height 40; relative
    // to origin {100,50} the top-left becomes {20,10}.
    expect(rect).toEqual({ left: 20, top: 10, width: 140, height: 40 });
  });

  it("ignores collapsed / zero-area rects and returns null when none remain", () => {
    expect(
      unionRectsRelativeTo([{ left: 10, top: 10, right: 10, bottom: 20 }], { left: 0, top: 0 }),
    ).toBeNull();
  });
});

describe("viewportRectToBbox <-> bboxToViewportRect round trip", () => {
  it("inverts the deep-zoom mapping back to PDF points", () => {
    const bbox = [100, 200, 300, 400]; // x0,y0,x1,y1 PDF points
    const pixelRect = bboxToViewportRect(bbox, PAGE_W, PAGE_H, { width: VIEW_W, height: VIEW_H });
    expect(pixelRect).not.toBeNull();
    const back = viewportRectToBbox(pixelRect!, PAGE_W, PAGE_H, VIEW_W, VIEW_H);
    expect(back).not.toBeNull();
    for (let i = 0; i < 4; i++) {
      expect(back![i]).toBeCloseTo(bbox[i]!, 6);
    }
  });

  it("round-trips at a non-unit zoom (rendered px != points)", () => {
    const bbox = [50, 100, 150, 260];
    const vw = PAGE_W * 1.5;
    const vh = PAGE_H * 1.5;
    const pixelRect = bboxToViewportRect(bbox, PAGE_W, PAGE_H, { width: vw, height: vh });
    const back = viewportRectToBbox(pixelRect!, PAGE_W, PAGE_H, vw, vh);
    for (let i = 0; i < 4; i++) {
      expect(back![i]).toBeCloseTo(bbox[i]!, 6);
    }
  });

  it("returns null on unusable dimensions", () => {
    expect(viewportRectToBbox({ left: 0, top: 0, width: 0, height: 10 }, PAGE_W, PAGE_H, VIEW_W, VIEW_H)).toBeNull();
    expect(viewportRectToBbox({ left: 0, top: 0, width: 10, height: 10 }, 0, PAGE_H, VIEW_W, VIEW_H)).toBeNull();
  });
});

describe("bboxesOverlap / findOverlappingRegion", () => {
  it("detects overlap order-independently", () => {
    expect(bboxesOverlap([0, 0, 10, 10], [5, 5, 15, 15])).toBe(true);
    // reversed tuple order still overlaps
    expect(bboxesOverlap([10, 10, 0, 0], [15, 15, 5, 5])).toBe(true);
    expect(bboxesOverlap([0, 0, 10, 10], [20, 20, 30, 30])).toBe(false);
  });

  it("picks the region with the largest intersection on the same page", () => {
    const regions: Region[] = [
      { id: "small", page: 3, bbox: [0, 0, 6, 6] },
      { id: "big", page: 3, bbox: [4, 4, 40, 40] },
      { id: "otherpage", page: 4, bbox: [0, 0, 100, 100] },
    ];
    const hit = findOverlappingRegion([5, 5, 30, 30], regions, 3);
    expect(hit?.id).toBe("big");
  });

  it("ignores regions on other pages and regions without id/bbox", () => {
    const regions: Region[] = [
      { id: "wrongpage", page: 9, bbox: [0, 0, 100, 100] },
      { kind: "noid", page: 3, bbox: [0, 0, 100, 100] },
      { id: "nobbox", page: 3 },
    ];
    expect(findOverlappingRegion([10, 10, 20, 20], regions, 3)).toBeNull();
  });
});

describe("buildTextSourceRef", () => {
  it("captures quote + page + bbox", () => {
    const ref = buildTextSourceRef({
      slug: "doc-a",
      page: 7,
      quote: "  Rated power 75 kW  ",
      bbox: [100, 200, 300, 220],
      regions: [],
    });
    expect(ref).toEqual({
      slug: "doc-a",
      page: 7,
      bbox: [100, 200, 300, 220],
      detail: { quote: "Rated power 75 kW" },
    });
    expect(ref?.region_id).toBeUndefined();
  });

  it("stamps region_id when the selection overlaps a gold region", () => {
    const ref = buildTextSourceRef({
      slug: "doc-a",
      page: 2,
      quote: "75 kW",
      bbox: [110, 205, 160, 215],
      regions: [{ id: "region-42", page: 2, bbox: [100, 200, 300, 240] }],
    });
    expect(ref?.region_id).toBe("region-42");
    expect(ref?.detail?.quote).toBe("75 kW");
  });

  it("returns null for an empty quote or missing bbox", () => {
    expect(buildTextSourceRef({ slug: "d", page: 1, quote: "   ", bbox: [0, 0, 1, 1], regions: [] })).toBeNull();
    expect(buildTextSourceRef({ slug: "d", page: 1, quote: "x", bbox: null, regions: [] })).toBeNull();
  });
});

describe("buildRegionSourceRef", () => {
  it("captures region bbox + region_id", () => {
    const ref = buildRegionSourceRef({
      slug: "doc-a",
      page: 4,
      region: { id: "tbl-1", page: 4, bbox: [10, 20, 110, 220], kind: "table" },
    });
    expect(ref).toEqual({
      slug: "doc-a",
      page: 4,
      bbox: [10, 20, 110, 220],
      region_id: "tbl-1",
    });
    expect(ref?.detail).toBeUndefined();
  });

  it("returns null when the region has no bbox", () => {
    expect(buildRegionSourceRef({ slug: "d", page: 1, region: { id: "x", page: 1 } })).toBeNull();
  });
});

describe("defaultReferenceLabel", () => {
  it("quotes a short selection and truncates a long one", () => {
    expect(defaultReferenceLabel({ quote: "Rated power", page: 1 })).toBe('"Rated power"');
    const long = "a".repeat(80);
    const label = defaultReferenceLabel({ quote: long, page: 1 });
    expect(label.length).toBeLessThan(long.length);
    expect(label.endsWith('..."')).toBe(true);
  });

  it("describes a region by kind + title + page", () => {
    expect(
      defaultReferenceLabel({ region: { id: "t", kind: "table", title: "Specs" }, page: 5 }),
    ).toBe("table: Specs (p.5)");
  });
});
