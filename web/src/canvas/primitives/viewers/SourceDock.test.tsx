/**
 * SourceDock layout-state tests (#110a).
 *
 * Pins the split-screen behaviour at the component boundary: the dock renders
 * only in "dock" mode, it is ONE shared pane (opening a second document swaps
 * content in place rather than mounting a second instance), and closing it
 * returns to canvas-full. The real PdfSourceView is stubbed so these tests run
 * without PDF.js in jsdom.
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
import { useUiStore } from "@/stores/uiStore";

import { SourceDock } from "./SourceDock";

vi.mock("./PdfSourceView", () => ({
  PdfSourceView: ({ slug, page, total, generation }: { slug: string; page: number; total: number; generation?: string }) => (
    <div data-testid="pdf-source-view" data-slug={slug} data-page={page} data-total={total} data-generation={generation} />
  ),
}));

beforeEach(() => {
  useUiStore.setState({ pdfViewer: null });
  vi.spyOn(documents, "index").mockResolvedValue({
    document: { page_count: 5, title: "Doc", filename: "doc.pdf" },
    outline: [],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
});

afterEach(() => {
  vi.useRealTimers();
  useUiStore.setState({ pdfViewer: null });
  vi.restoreAllMocks();
});

async function renderDock() {
  await act(async () => {
    render(<SourceDock />);
  });
}

describe("SourceDock", () => {
  it("refreshes an open LKH viewer from four pages to its published one-page generation", async () => {
    vi.useFakeTimers();
    vi.mocked(documents.index).mockResolvedValue({
      document: { page_count: 4, title: "Alfa Laval LKH", filename: "Alfa Laval LKH.pdf" }, outline: [],
    });
    await act(async () => { useUiStore.getState().openPdf("lkh-g4-shrink", { page: 2 }); });
    await renderDock();
    expect(screen.getByTestId("pdf-source-view").getAttribute("data-total")).toBe("4");
    vi.mocked(documents.index).mockResolvedValue({
      document: { page_count: 1, title: "Alfa Laval LKH", filename: "Alfa Laval LKH.pdf",
        generation: { id: "replacement-b", pages: [1] } }, outline: [],
    } as Awaited<ReturnType<typeof documents.index>>);
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    const view = screen.getByTestId("pdf-source-view");
    expect(view.getAttribute("data-total")).toBe("1");
    expect(view.getAttribute("data-generation")).toBe("replacement-b");
    expect(view.getAttribute("data-page")).toBe("1");
  });

  it("renders nothing when no document is open", async () => {
    await renderDock();
    expect(screen.queryByTestId("source-dock")).toBeNull();
  });

  it("renders nothing in modal mode (modal owns that surface)", async () => {
    await renderDock();
    await act(async () => {
      useUiStore.getState().openPdf("doc-a", { page: 1, mode: "modal" });
    });
    expect(screen.queryByTestId("source-dock")).toBeNull();
  });

  it("renders the docked pane in dock mode", async () => {
    await renderDock();
    await act(async () => {
      useUiStore.getState().openPdf("doc-a", { page: 2 });
    });
    expect(screen.getByTestId("source-dock")).toBeTruthy();
    const view = screen.getByTestId("pdf-source-view");
    expect(view.getAttribute("data-slug")).toBe("doc-a");
    expect(view.getAttribute("data-page")).toBe("2");
  });

  it("is one shared pane: opening a second document swaps content in place", async () => {
    await renderDock();
    await act(async () => {
      useUiStore.getState().openPdf("doc-a", { page: 1 });
    });
    await act(async () => {
      useUiStore.getState().openPdf("doc-b", { page: 4 });
    });
    // Still exactly one dock + one viewer instance, content swapped.
    expect(screen.getAllByTestId("source-dock")).toHaveLength(1);
    const views = screen.getAllByTestId("pdf-source-view");
    expect(views).toHaveLength(1);
    expect(views[0]!.getAttribute("data-slug")).toBe("doc-b");
    expect(views[0]!.getAttribute("data-page")).toBe("4");
  });

  it("sizes the pane as a fraction of the viewport, not of the space beside the explorer", async () => {
    useUiStore.getState().setSourceDockRatio(0.6);
    await renderDock();
    await act(async () => {
      useUiStore.getState().openPdf("doc-a", { page: 1 });
    });
    const dock = screen.getByTestId("source-dock");
    // The pane overlays the page instead of sharing the row, so its width no
    // longer depends on the explorer. That is what gives the pages room: they
    // used to get whatever was left between the explorer and the canvas.
    // Normalised by the CSS parser: 0.6 * 100vw -> 60vw. The point is that it
    // is a share of the VIEWPORT, with no explorer term in it at all.
    expect(dock.style.width).toBe("calc(60vw)");
    expect(dock.style.maxWidth).toBe("85vw");
    expect(dock.style.width).not.toContain("px");
  });

  it("overlays the page rather than taking part in its layout", async () => {
    await renderDock();
    await act(async () => {
      useUiStore.getState().openPdf("doc-a", { page: 1 });
    });
    const dock = screen.getByTestId("source-dock");
    // Fixed + left-anchored: the canvas underneath never reflows when the
    // viewer opens or closes, and the pane can cover the files explorer.
    expect(dock.className).toContain("fixed");
    expect(dock.className).toContain("left-0");
  });

  it("closing the dock returns to canvas-full (unmounts the pane)", async () => {
    await renderDock();
    await act(async () => {
      useUiStore.getState().openPdf("doc-a", { page: 1 });
    });
    expect(screen.getByTestId("source-dock")).toBeTruthy();
    await act(async () => {
      useUiStore.getState().closePdf();
    });
    expect(screen.queryByTestId("source-dock")).toBeNull();
  });
});
