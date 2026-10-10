import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
import { PdfSourceView } from "./PdfSourceView";
import { loadPdf } from "./pdfjs";

const state = vi.hoisted(() => ({ complete: null as (() => void) | null }));

vi.mock("./pdfjs", () => ({
  loadPdf: vi.fn(async () => ({
    doc: { numPages: 1, getOutline: async () => [], getPage: async () => ({ getTextContent: async () => ({ items: [] }) }) },
    destroy: async () => {},
  })),
  pageSizes: async () => ({ 1: { w: 100, h: 200 } }),
}));

vi.mock("./PdfPageCanvas", async () => {
  const { useEffect } = await import("react");
  return {
    PdfPageCanvas: ({ page, zoom, onRendered }: {
      page: number; zoom: number; onRendered: (page: number, size: { w: number; h: number; zoom: number }) => void;
    }) => {
      useEffect(() => {
        const complete = () => onRendered(page, { w: 100 * zoom, h: 200 * zoom, zoom });
        if (zoom === 1) complete();
        else state.complete = complete;
      }, [page, zoom, onRendered]);
      return <canvas data-testid="delayed-pdf-canvas" />;
    },
  };
});

beforeEach(() => {
  state.complete = null;
  vi.spyOn(documents, "regions").mockResolvedValue([]);
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  HTMLElement.prototype.scrollTo = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("PDF viewer render state", () => {
  it("shows a whole-view error for a failed PDF worker", async () => {
    vi.mocked(loadPdf).mockRejectedValueOnce(new Error("worker failed to boot"));
    render(<PdfSourceView slug="manual" page={1} total={1} onPageChange={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Could not load PDF: worker failed to boot");
    expect(console.error).toHaveBeenCalled();
  });

  it("scales the last completed raster alongside overlays until 400% is ready", async () => {
    render(<PdfSourceView slug="manual" page={1} total={1} onPageChange={vi.fn()}
      highlightPage={1} highlightBbox={[10, 20, 30, 40]} />);
    const canvas = await screen.findByTestId("delayed-pdf-canvas");
    for (let step = 0; step < 15; step++) fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await waitFor(() => expect(state.complete).not.toBeNull());
    expect(canvas.parentElement!.style.transform).toBe("scale(4)");
    expect(screen.getByTestId("pdf-page-slot").style.width).toBe("400px");
    expect(screen.getByTestId("pdf-highlight").style.width).toBe("80px");
    await act(async () => { state.complete!(); });
    expect(canvas.parentElement!.style.transform).toBe("");
    expect(screen.getByTestId("pdf-highlight").style.width).toBe("80px");
  });
});
