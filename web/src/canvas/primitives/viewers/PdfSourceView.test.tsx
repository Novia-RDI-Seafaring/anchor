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
  await act(async () => {
    render(
      <PdfSourceView
        slug="doc-a"
        page={1}
        total={PAGE_COUNT}
        onPageChange={onPageChange}
        {...props}
      />,
    );
  });
  // Let loadPdf + pageSizes resolve.
  await waitFor(() => expect(screen.getByTestId("thumbnail-rail")).toBeTruthy());
  return { onPageChange };
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
    // The highlight rect is drawn on page 5's slot.
    const highlight = await screen.findByTestId("pdf-highlight");
    const slot = highlight.closest("[data-testid='pdf-page-slot']");
    expect(slot?.getAttribute("data-page")).toBe("5");
  });

  it("jumps straight to the target instead of animating the trip", async () => {
    // Opening a source ref should PUT you at the evidence. The pages in
    // between are not the answer, and with the viewer opening on hover the
    // animation replayed on every link the pointer touched.
    const calls: ScrollToOptions[] = [];
    stubScroller();
    const realScrollTo = HTMLElement.prototype.scrollTo;
    HTMLElement.prototype.scrollTo = function scrollTo(opts: ScrollToOptions | number) {
      if (typeof opts === "object") calls.push(opts);
    } as typeof HTMLElement.prototype.scrollTo;
    try {
      await renderViewer({ highlightPage: 5, highlightBbox: [10, 20, 40, 60] });
      await waitFor(() => expect(calls.length).toBeGreaterThan(0));
      for (const c of calls) expect(c.behavior).not.toBe("smooth");
    } finally {
      HTMLElement.prototype.scrollTo = realScrollTo;
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
