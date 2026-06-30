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
  PdfSourceView: ({ slug, page }: { slug: string; page: number }) => (
    <div data-testid="pdf-source-view" data-slug={slug} data-page={page} />
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
  useUiStore.setState({ pdfViewer: null });
  vi.restoreAllMocks();
});

async function renderDock() {
  await act(async () => {
    render(<SourceDock />);
  });
}

describe("SourceDock", () => {
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

  it("applies the dock ratio as the pane width", async () => {
    useUiStore.getState().setSourceDockRatio(0.6);
    await renderDock();
    await act(async () => {
      useUiStore.getState().openPdf("doc-a", { page: 1 });
    });
    const dock = screen.getByTestId("source-dock");
    expect(dock.style.width).toBe("60%");
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
