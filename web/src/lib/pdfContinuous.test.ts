/**
 * Continuous-viewer layout math tests (#220 part A).
 *
 * These pin the stacked page layout the Preview-style viewer relies on:
 * cumulative page offsets, scroll-to-page targets, page-in-view detection,
 * the virtualization window, and the deep-zoom highlight scroll target.
 */
import { describe, expect, it } from "vitest";

import {
  PAGE_GAP,
  anchorAt,
  buildPageLayout,
  pageInView,
  pointForAnchor,
  scrollTopForPage,
  scrollTopForPageRect,
  visiblePageRange,
  wheelZoom,
} from "./pdfContinuous";

const fallback = { w: 100, h: 200 };

describe("buildPageLayout", () => {
  it("stacks pages with their height + gap and accumulates the top offset", () => {
    const sizes = { 1: { w: 100, h: 200 }, 2: { w: 100, h: 300 } };
    const { items, totalHeight } = buildPageLayout(3, sizes, 1, fallback);
    expect(items).toHaveLength(3);
    expect(items[0]).toMatchObject({ page: 1, height: 200, top: 0 });
    // page 2 starts after page 1 height + gap.
    expect(items[1]).toMatchObject({ page: 2, height: 300, top: 200 + PAGE_GAP });
    // page 3 falls back to the default size, after page 2.
    expect(items[2]).toMatchObject({ page: 3, height: 200, top: 200 + PAGE_GAP + 300 + PAGE_GAP });
    // total height excludes the trailing gap.
    expect(totalHeight).toBe(200 + PAGE_GAP + 300 + PAGE_GAP + 200);
  });

  it("scales heights and widths by zoom", () => {
    const { items } = buildPageLayout(1, { 1: { w: 100, h: 200 } }, 2, fallback);
    expect(items[0]!.height).toBe(400);
    expect(items[0]!.width).toBe(200);
  });
});

describe("scrollTopForPage", () => {
  const { items, totalHeight } = buildPageLayout(5, {}, 1, fallback);

  it("targets a page's top edge minus a margin", () => {
    // page 3 top = 2 * (200 + gap)
    const expectedTop = 2 * (200 + PAGE_GAP);
    expect(scrollTopForPage(items, 3, 400, totalHeight, PAGE_GAP)).toBe(expectedTop - PAGE_GAP);
  });

  it("clamps to the content bottom", () => {
    const off = scrollTopForPage(items, 5, 400, totalHeight, 0);
    expect(off).toBeLessThanOrEqual(Math.max(0, totalHeight - 400));
    expect(off).toBe(Math.max(0, totalHeight - 400));
  });

  it("never goes negative for the first page", () => {
    expect(scrollTopForPage(items, 1, 400, totalHeight)).toBe(0);
  });
});

describe("pageInView", () => {
  const { items } = buildPageLayout(5, {}, 1, fallback);
  const step = 200 + PAGE_GAP;

  it("reports the page filling the viewport top", () => {
    expect(pageInView(items, 0, 400)).toBe(1);
  });

  it("switches to the page whose area dominates after scrolling", () => {
    // Scroll so page 3 occupies most of a short viewport.
    expect(pageInView(items, 2 * step, 100)).toBe(3);
  });
});

describe("visiblePageRange", () => {
  const { items } = buildPageLayout(10, {}, 1, fallback);
  const step = 200 + PAGE_GAP;

  it("renders the overlapping page plus overscan neighbours", () => {
    // Viewport sits squarely on page 4.
    const { start, end } = visiblePageRange(items, 3 * step + 10, 100, 1);
    expect(start).toBe(3);
    expect(end).toBe(5);
  });

  it("does not run off the ends", () => {
    const head = visiblePageRange(items, 0, 100, 2);
    expect(head.start).toBe(1);
    const tail = visiblePageRange(items, 9 * step, 100, 2);
    expect(tail.end).toBe(10);
  });
});

describe("scrollTopForPageRect", () => {
  const { items, totalHeight } = buildPageLayout(5, {}, 1, fallback);

  it("centres a within-page rect using the page's stacked offset", () => {
    // A rect 50px down inside page 2, height 20, container 100 tall.
    const page2Top = 200 + PAGE_GAP;
    const expected = page2Top + 50 + 10 - 50; // absoluteCentre - containerH/2
    expect(scrollTopForPageRect(items, 2, 50, 20, 100, totalHeight)).toBe(expected);
  });

  it("clamps to the content bounds", () => {
    const off = scrollTopForPageRect(items, 5, 180, 10, 100, totalHeight);
    expect(off).toBeLessThanOrEqual(Math.max(0, totalHeight - 100));
  });
});

describe("wheelZoom", () => {
  it("zooms in on wheel up and out on wheel down, about 15% per mouse notch", () => {
    const up = wheelZoom(1, -100, 0, false, 0.4, 4);
    const down = wheelZoom(1, 100, 0, false, 0.4, 4);
    expect(up).toBeGreaterThan(1.1);
    expect(up).toBeLessThan(1.2);
    expect(down).toBeLessThan(0.9);
    expect(down).toBeGreaterThan(0.8);
  });

  it("is symmetric: in then out by the same delta returns to the start", () => {
    expect(wheelZoom(wheelZoom(1, -40, 0, false, 0.4, 4), 40, 0, false, 0.4, 4)).toBeCloseTo(1, 2);
  });

  it("boosts small pinch deltas so a trackpad pinch is not sluggish", () => {
    expect(wheelZoom(1, -5, 0, true, 0.4, 4)).toBeCloseTo(wheelZoom(1, -50, 0, false, 0.4, 4), 3);
  });

  it("treats line-mode deltas as larger steps", () => {
    expect(wheelZoom(1, -3, 1, false, 0.4, 4)).toBeGreaterThan(1.1);
  });

  it("clamps to the min and max", () => {
    expect(wheelZoom(3.9, -1000, 0, false, 0.4, 4)).toBe(4);
    expect(wheelZoom(0.45, 1000, 0, false, 0.4, 4)).toBe(0.4);
  });
});

describe("zoom anchor", () => {
  it("keeps the same spot on the same page across a zoom change", () => {
    const sizes = { 1: { w: 100, h: 200 }, 2: { w: 100, h: 200 }, 3: { w: 100, h: 200 } };
    const before = buildPageLayout(3, sizes, 1, fallback);
    // A point a quarter of the way down page 2, halfway across.
    const y = before.items[1]!.top + 50;
    const anchor = anchorAt(before.items, 100, 50, y)!;
    expect(anchor).toEqual({ page: 2, fy: 0.25, fx: 0.5 });

    const after = buildPageLayout(3, sizes, 2, fallback);
    const pt = pointForAnchor(after.items, 200, anchor)!;
    expect(pt.x).toBe(100);
    expect(pt.y).toBe(after.items[1]!.top + 100);
  });

  it("assigns a point in the gap below a page to that page", () => {
    const { items } = buildPageLayout(2, {}, 1, fallback);
    const anchor = anchorAt(items, 100, 0, items[0]!.height + PAGE_GAP / 2)!;
    expect(anchor.page).toBe(1);
    expect(anchor.fy).toBeGreaterThan(1);
  });
});
