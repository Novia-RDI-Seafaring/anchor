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
  buildPageLayout,
  pageInView,
  scrollTopForPage,
  scrollTopForPageRect,
  visiblePageRange,
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
