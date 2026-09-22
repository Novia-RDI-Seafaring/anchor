/**
 * PdfSourceView (continuous Preview-style viewer) component tests (#220 part A).
 *
 * PDF.js is mocked: the document loader returns a fake doc with known page
 * sizes, and the per-page canvas is stubbed so these run in jsdom without the
 * worker. The tests pin the new behaviour: a thumbnail rail with one thumb per
 * page (toggleable), clicking a thumbnail scrolls to that page, scrolling
 * updates the in-view page (onPageChange), and a deep-zoom highlight scrolls the
 * continuous view to the target page and draws the highlight there.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";

import { requestViewerZoom } from "@/canvas/viewerZoom";

import { PdfSourceView } from "./PdfSourceView";

const PAGE_COUNT = 6;

// Fake PDF doc: 6 pages, each 100x200 points.
function makeDoc() {
  return {
    numPages: PAGE_COUNT,
    getPage: vi.fn(async (_p: number) => ({
      view: [0, 0, 100, 200],
      getViewport: ({ scale }: { scale: number }) => ({ width: 100 * scale, height: 200 * scale }),
    })),
  };
}

vi.mock("./pdfjs", async () => {
  return {
    loadPdf: vi.fn(async () => ({ doc: makeDoc(), destroy: async () => {} })),
    pageSizes: vi.fn(async () => {
      const out: Record<number, { w: number; h: number }> = {};
      for (let p = 1; p <= PAGE_COUNT; p++) out[p] = { w: 100, h: 200 };
      return out;
    }),
  };
});

// Stub the heavy per-page canvas; report a deterministic rendered size so the
// overlays (highlight) have geometry to draw against.
vi.mock("./PdfPageCanvas", () => ({
  PdfPageCanvas: ({
    page,
    zoom,
    onRendered,
  }: {
    page: number;
    zoom: number;
    onRendered?: (p: number, s: { w: number; h: number }) => void;
  }) => {
    onRendered?.(page, { w: 100 * zoom, h: 200 * zoom });
    return <div data-testid="page-canvas-stub" data-page={page} />;
  },
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  vi.spyOn(documents, "regions").mockResolvedValue([]);
  vi.spyOn(documents, "pageImageUrl").mockImplementation((slug, p) => `img:${slug}:${p}`);
  vi.spyOn(documents, "pdfUrl").mockImplementation((slug) => `pdf:${slug}`);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// jsdom has no layout: give the scroller a fixed clientHeight and a capturing
// scrollTo so we can assert scroll targets and simulate scroll position.
function stubScroller(target: number | null = null): { lastTop: () => number | null } {
  let lastTop: number | null = target;
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() {
      return this.getAttribute?.("data-testid") === "pdf-scroller" ? 400 : 0;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() {
      return this.getAttribute?.("data-testid") === "pdf-scroller" ? 300 : 0;
    },
  });
  HTMLElement.prototype.scrollTo = function scrollTo(opts: ScrollToOptions | number) {
    if (typeof opts === "object" && opts.top != null) lastTop = opts.top;
  } as typeof HTMLElement.prototype.scrollTo;
  return { lastTop: () => lastTop };
}

async function renderViewer(props?: Partial<Parameters<typeof PdfSourceView>[0]>) {
  const onPageChange = vi.fn();
  const view = (extra?: Partial<Parameters<typeof PdfSourceView>[0]>) => (
    <PdfSourceView
      slug="doc-a"
      page={1}
      total={PAGE_COUNT}
      onPageChange={onPageChange}
      {...props}
      {...extra}
    />
  );
  let rendered!: ReturnType<typeof render>;
  await act(async () => {
    rendered = render(view());
  });
  // Let loadPdf + pageSizes resolve.
  await waitFor(() => expect(screen.getByTestId("thumbnail-rail")).toBeTruthy());
  const rerender = async (extra: Partial<Parameters<typeof PdfSourceView>[0]>) => {
    await act(async () => {
      rendered.rerender(view(extra));
    });
  };
  return { onPageChange, rerender };
}

describe("PdfSourceView (continuous)", () => {
  it("renders a thumbnail rail with one thumbnail per page", async () => {
    stubScroller();
    await renderViewer();
    const thumbs = screen.getAllByTestId("thumbnail");
    expect(thumbs).toHaveLength(PAGE_COUNT);
    expect(thumbs[0]!.getAttribute("data-page")).toBe("1");
  });

  it("hides the rail when toggled off", async () => {
    stubScroller();
    await renderViewer();
    fireEvent.click(screen.getByLabelText("Toggle thumbnails"));
    expect(screen.queryByTestId("thumbnail-rail")).toBeNull();
  });

  it("clicking a thumbnail scrolls the continuous view to that page", async () => {
    const scroller = stubScroller();
    await renderViewer();
    const thumb4 = screen.getAllByTestId("thumbnail").find((t) => t.getAttribute("data-page") === "4")!;
    await act(async () => {
      fireEvent.click(thumb4);
    });
    // page 4 top = 3 * (200 + gap=16) = 648, minus margin 16 -> 632.
    expect(scroller.lastTop()).toBe(632);
  });

  it("scrolling updates the in-view page via onPageChange", async () => {
    stubScroller();
    const { onPageChange } = await renderViewer();
    const view = screen.getByTestId("pdf-scroller");
    // Scroll so page 3 dominates a 400px viewport.
    await act(async () => {
      Object.defineProperty(view, "scrollTop", { configurable: true, value: 2 * (200 + 16) });
      fireEvent.scroll(view);
    });
    await waitFor(() => expect(onPageChange).toHaveBeenCalledWith(3));
  });

  it("deep-zoom highlight scrolls to the target page and draws the highlight there", async () => {
    const scroller = stubScroller();
    await renderViewer({ highlightPage: 5, highlightBbox: [10, 20, 40, 60] });
    // Should have scrolled toward page 5 (well past the first pages).
    await waitFor(() => {
      const top = scroller.lastTop();
      expect(top).not.toBeNull();
      expect(top!).toBeGreaterThan(3 * (200 + 16));
    });
    // The mark lives above the stacked pages rather than inside one of them,
    // so that it can travel between two refs instead of blinking out on one
    // page and in on another. So "drawn on page 5" is now a question about
    // where it sits, not about which slot owns it.
    const highlight = await screen.findByTestId("pdf-highlight");
    expect(highlight.closest("[data-testid='pdf-page-slot']")).toBeNull();
    const top = parseFloat(highlight.style.top);
    const pageTop = 4 * (200 + 16);
    expect(top).toBeGreaterThanOrEqual(pageTop);
    expect(top).toBeLessThan(pageTop + 200);
  });

  it("flies to the next ref instead of blinking out and in", async () => {
    stubScroller();
    const { rerender } = await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightNonce: 1,
    });
    const first = await screen.findByTestId("pdf-highlight");
    // Nowhere to fly from on the first mark: it simply appears.
    expect(first.className).not.toContain("anchor-mark-flying");
    const wasAt = first.style.top;

    await rerender({ highlightPage: 2, highlightBbox: [10, 120, 40, 160], highlightNonce: 2 });
    const moved = await screen.findByTestId("pdf-highlight");
    // Same element, travelling -- not a new one in a new place.
    expect(moved).toBe(first);
    expect(moved.className).toContain("anchor-mark-flying");
    expect(moved.style.top).not.toBe(wasAt);
  });

  it("takes the shape of what it lands on", async () => {
    stubScroller();
    const { rerender } = await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 200, 60],
      highlightNonce: 1,
    });
    const mark = await screen.findByTestId("pdf-highlight");
    const wide = parseFloat(mark.style.width);

    await rerender({ highlightPage: 2, highlightBbox: [10, 20, 30, 28], highlightNonce: 2 });
    expect(parseFloat(mark.style.width)).toBeLessThan(wide);
  });

  it("sits exactly on the referenced box, not on its neighbours", async () => {
    stubScroller();
    // A single table cell. Padding the mark up to a readable minimum was tried
    // and it spilled onto the rows above and below, marking values it does not
    // name -- so the mark stays the size of the thing it points at.
    await renderViewer({ highlightPage: 2, highlightBbox: [10, 20, 12, 22], highlightNonce: 1 });
    const mark = await screen.findByTestId("pdf-highlight");
    expect(parseFloat(mark.style.width)).toBeLessThan(15);
    expect(parseFloat(mark.style.height)).toBeLessThan(15);
  });

  it("draws one mark per place a reference points at", async () => {
    stubScroller();
    await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [
        { page: 2, bbox: [100, 200, 110, 210], precision: "item" },
      ],
      highlightNonce: 1,
    });
    await waitFor(() =>
      expect(screen.getAllByTestId("pdf-highlight")).toHaveLength(2),
    );
  });

  it("travels every mark, pairing them by kind so neither crosses over", async () => {
    // Both marks move, so the eye can follow each to where it went. Paired by
    // position in the list instead, the cell mark and the callout mark would
    // swap places on screen and describe a movement that did not happen.
    stubScroller();
    const { rerender } = await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [{ page: 2, bbox: [100, 200, 110, 210], precision: "item" }],
      highlightNonce: 1,
    });
    const keyOf = () =>
      screen.getAllByTestId("pdf-highlight").map((el) => el.getAttribute("data-mark-kind"));
    expect(keyOf()).toEqual(["primary#0", "item#0"]);

    const before = screen.getAllByTestId("pdf-highlight");
    await rerender({
      highlightPage: 2,
      highlightBbox: [10, 300, 40, 340],
      highlightAlso: [{ page: 2, bbox: [400, 500, 410, 510], precision: "item" }],
      highlightNonce: 2,
    });
    const after = screen.getAllByTestId("pdf-highlight");
    // The same elements, moved -- not new ones in new places.
    expect(after[0]).toBe(before[0]);
    expect(after[1]).toBe(before[1]);
    for (const el of after) expect(el.className).toContain("anchor-mark-flying");
    expect(keyOf()).toEqual(["primary#0", "item#0"]);
  });

  it("tells two places of the same kind apart", async () => {
    stubScroller();
    await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [
        { page: 2, bbox: [100, 200, 110, 210], precision: "cell" },
        { page: 2, bbox: [300, 200, 310, 210], precision: "cell" },
      ],
      highlightNonce: 1,
    });
    await waitFor(() =>
      expect(
        screen.getAllByTestId("pdf-highlight").map((el) => el.getAttribute("data-mark-kind")),
      ).toEqual(["primary#0", "cell#0", "cell#1"]),
    );
  });

  it("still draws the primary when an extra place has no geometry", async () => {
    // A highlight that never appears is worse than a partial one.
    stubScroller();
    await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      highlightAlso: [{ page: 2, bbox: [1, 2] as any, precision: "item" }],
      highlightNonce: 1,
    });
    await waitFor(() => expect(screen.getAllByTestId("pdf-highlight")).toHaveLength(1));
  });

  it("traces a stroke rather than boxing it", async () => {
    // A dimension is a span between two witness lines. A box around it would
    // cover the part of the drawing the span is measuring.
    stubScroller();
    await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [
        { page: 2, bbox: [100, 200, 160, 200], precision: "line",
          line: [100, 200, 160, 200] },
      ],
      highlightNonce: 1,
    });
    const stroke = await screen.findByTestId("pdf-highlight-stroke");
    expect(stroke.querySelector("polyline")?.getAttribute("points")).toBeTruthy();
    // And it is NOT also drawn as a box.
    expect(screen.getAllByTestId("pdf-highlight")).toHaveLength(1);
  });

  it("draws a stroke of more than two points", async () => {
    stubScroller();
    await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [
        { page: 2, bbox: [100, 100, 200, 200], precision: "line",
          line: [100, 100, 200, 100, 200, 200] },
      ],
      highlightNonce: 1,
    });
    const stroke = await screen.findByTestId("pdf-highlight-stroke");
    const pts = stroke.querySelector("polyline")!.getAttribute("points")!;
    expect(pts.trim().split(/\s+/)).toHaveLength(3);
  });

  it("ignores a stroke with an odd or too-short run of coordinates", async () => {
    stubScroller();
    await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { page: 2, bbox: [0, 0, 1, 1], precision: "line", line: [1, 2] as any },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { page: 2, bbox: [0, 0, 1, 1], precision: "line", line: [1, 2, 3] as any },
      ],
      highlightNonce: 1,
    });
    await waitFor(() => expect(screen.getAllByTestId("pdf-highlight")).toHaveLength(1));
    expect(screen.queryByTestId("pdf-highlight-stroke")).toBeNull();
  });

  it("zooms when the reader wheels over a reference out in the canvas", async () => {
    stubScroller();
    await renderViewer({ highlightPage: 2, highlightBbox: [10, 20, 40, 60], highlightNonce: 1 });
    const zoomLabel = () => screen.getByLabelText("Reset zoom").textContent;
    const before = zoomLabel();
    await act(async () => {
      requestViewerZoom(-120, 0);
    });
    expect(zoomLabel()).not.toBe(before);
  });

  it("zooms out only far enough to fit a reference that names several places", async () => {
    // A reference that already fits keeps whatever zoom the reader set. That
    // is the whole point of them setting it.
    stubScroller();
    const { rerender } = await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightNonce: 1,
    });
    const read = () => parseInt(screen.getByLabelText("Reset zoom").textContent!, 10);
    const fitting = read();

    // Now one whose places span far more than the pane can show at this zoom.
    await rerender({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [{ page: 2, bbox: [10, 20000, 40, 20040], precision: "item" }],
      highlightNonce: 2,
    });
    expect(read()).toBeLessThan(fitting);
  });

  it("ignores places on another page when deciding what has to fit", async () => {
    // No zoom shows two pages at once, so a place elsewhere is not a reason
    // to shrink the one the reader is looking at.
    stubScroller();
    const { rerender } = await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightNonce: 1,
    });
    const read = () => parseInt(screen.getByLabelText("Reset zoom").textContent!, 10);
    const before = read();
    await rerender({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightAlso: [{ page: 5, bbox: [10, 20000, 40, 20040], precision: "item" }],
      highlightNonce: 2,
    });
    expect(read()).toBe(before);
  });

  it("brings the page to a mark that landed out of sight, once it has landed", async () => {
    // The mark travels first; only then does it take hold of the page. Moving
    // both at once reads as everything sliding, and what went where is lost.
    const scroller = stubScroller(0);
    const tops: (number | null)[] = [];
    const { rerender } = await renderViewer({
      highlightPage: 2,
      highlightBbox: [10, 20, 40, 60],
      highlightNonce: 1,
    });
    // Let the arrival settle so later movement is this rule's doing.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 420));
    });
    const settled = scroller.lastTop();

    // Far down the same page, well past a 400px viewport.
    await rerender({ highlightPage: 2, highlightBbox: [10, 700, 40, 740], highlightNonce: 2 });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120));
    });
    tops.push(scroller.lastTop());   // still flying: page has not moved
    await act(async () => {
      await new Promise((r) => setTimeout(r, 400));
    });
    tops.push(scroller.lastTop());   // landed: page has been brought over

    expect(tops[0]).toBe(settled);
    expect(tops[1]).not.toBe(settled);
  });

  it("leaves the page alone for a mark that is already on screen", async () => {
    // A small jump at a readable zoom: the mark moves, the document does not.
    const scroller = stubScroller(0);
    const { rerender } = await renderViewer({
      highlightPage: 1,
      highlightBbox: [10, 20, 40, 60],
      highlightNonce: 1,
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 420));
    });
    const settled = scroller.lastTop();
    await rerender({ highlightPage: 1, highlightBbox: [10, 90, 40, 130], highlightNonce: 2 });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 420));
    });
    expect(scroller.lastTop()).toBe(settled);
  });

  function captureScrolls() {
    const calls: ScrollToOptions[] = [];
    const real = HTMLElement.prototype.scrollTo;
    HTMLElement.prototype.scrollTo = function scrollTo(opts: ScrollToOptions | number) {
      if (typeof opts === "object") calls.push(opts);
    } as typeof HTMLElement.prototype.scrollTo;
    return { calls, restore: () => { HTMLElement.prototype.scrollTo = real; } };
  }

  it("arrives instantly: opening at a ref does not animate the trip", async () => {
    // There is no "from" yet, so animating just makes you wait while pages you
    // did not ask for stream past -- and on hover it replayed per link.
    stubScroller();
    const { calls, restore } = captureScrolls();
    try {
      await renderViewer({ highlightPage: 5, highlightBbox: [10, 20, 40, 60] });
      await waitFor(() => expect(calls.length).toBeGreaterThan(0));
      for (const c of calls) expect(c.behavior).not.toBe("smooth");
    } finally {
      restore();
    }
  });

  it("animates the travel to a ref on another page once the viewer is open", async () => {
    // Now there IS a from: you can see one page and the next ref is on
    // another. Sliding keeps the two related; jumping would teleport.
    stubScroller();
    const { calls, restore } = captureScrolls();
    try {
      const { rerender } = await renderViewer({
        highlightPage: 2, highlightBbox: [10, 20, 40, 60], highlightNonce: 1,
      });
      await waitFor(() => expect(calls.length).toBeGreaterThan(0));
      const arrival = calls.length;

      await rerender({ highlightPage: 5, highlightBbox: [10, 20, 40, 60], highlightNonce: 2 });
      await waitFor(() => expect(calls.length).toBeGreaterThan(arrival));
      expect(calls[calls.length - 1]!.behavior).toBe("smooth");
    } finally {
      restore();
    }
  });

  it("does not move the page for a ref on the SAME page", async () => {
    // The page is already in front of the reader. Moving the whole document
    // to relocate a box that could simply have moved is the lurch that made
    // this feel busy.
    stubScroller();
    const { calls, restore } = captureScrolls();
    try {
      const { rerender } = await renderViewer({
        highlightPage: 3, highlightBbox: [10, 20, 40, 60], highlightNonce: 1,
      });
      await waitFor(() => expect(calls.length).toBeGreaterThan(0));
      const afterArrival = calls.length;

      await rerender({ highlightPage: 3, highlightBbox: [200, 400, 260, 430], highlightNonce: 2 });
      // Highlight moved, page did not.
      expect(calls.length).toBe(afterArrival);
    } finally {
      restore();
    }
  });

  it("keeps the highlight up instead of fading it after a few seconds", async () => {
    // Clicking a source ref means "check this value against its page", which
    // takes longer than a flash: read the card, read the page, look back. The
    // highlight used to disappear after 4 s, exactly when it was needed.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      stubScroller();
      await renderViewer({ highlightPage: 2, highlightBbox: [10, 20, 40, 60] });
      expect(await screen.findByTestId("pdf-highlight")).toBeTruthy();
      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });
      expect(screen.queryByTestId("pdf-highlight")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("outlines a region only while the cursor is over it", async () => {
    // Painting every gold region turned a four-page leaflet into a page of
    // dashed boxes that competed with the source highlight for attention.
    vi.spyOn(documents, "regions").mockResolvedValue([
      { id: "r1", bbox: [0, 0, 50, 50], kind: "table" },
      { id: "r2", bbox: [0, 100, 50, 150], kind: "text" },
    ] as never);
    stubScroller();
    await renderViewer({ canvasSlug: "board" });

    const rects = await screen.findAllByTestId("region-capture-rect");
    expect(rects.length).toBeGreaterThan(0);
    // Nothing is outlined until the cursor is over a region.
    for (const r of rects) {
      expect(r.getAttribute("stroke")).toBe("transparent");
      expect(r.getAttribute("data-hovered")).toBe("false");
    }
    // The click target survives: the rect is still in the DOM and clickable.
    expect(rects[0]!.getAttribute("pointer-events")).toBe("stroke");
  });

  it("dismisses the highlight on Escape, so it is never stuck", async () => {
    stubScroller();
    await renderViewer({ highlightPage: 2, highlightBbox: [10, 20, 40, 60] });
    expect(await screen.findByTestId("pdf-highlight")).toBeTruthy();
    await act(async () => {
      fireEvent.keyDown(window, { key: "Escape" });
    });
    await waitFor(() => expect(screen.queryByTestId("pdf-highlight")).toBeNull());
  });
});
