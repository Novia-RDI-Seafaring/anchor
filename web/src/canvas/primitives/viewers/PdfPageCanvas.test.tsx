import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PdfPageCanvas } from "./PdfPageCanvas";
import type { PdfDoc } from "./pdfjs";

const text = vi.hoisted(() => ({
  render: vi.fn<() => Promise<void>>(),
  cancel: vi.fn(),
}));
const selection = vi.hoisted(() => ({ dispose: vi.fn() }));

vi.mock("./pdfjs", () => ({
  getPdfLibrary: async () => ({
    TextLayer: class {
      constructor({ container, viewport }: { container: HTMLElement; viewport: { width: number } }) {
        container.textContent = `text at ${viewport.width}`;
      }
      render = text.render;
      cancel = text.cancel;
    },
  }),
}));

vi.mock("./textLayerSelection", () => ({ registerTextLayerSelection: () => selection.dispose }));

function deferred() {
  let resolve!: () => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<void>((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

function task() {
  return { ...deferred(), cancel: vi.fn() };
}

function cancellation() {
  return Object.assign(new Error("cancelled"), { name: "RenderingCancelledException" });
}

function makeDoc(renderPage = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })), rotation = 0) {
  const getPage = vi.fn(async () => ({
    getViewport: ({ scale }: { scale: number }) => ({ width: 100 * scale, height: 200 * scale, rotation }),
    render: renderPage,
    streamTextContent: () => ({}),
  }));
  return { doc: { numPages: 2, getPage } as unknown as PdfDoc, getPage, renderPage };
}

let drawImage: ReturnType<typeof vi.fn>;

beforeEach(() => {
  text.render.mockReset().mockResolvedValue();
  text.cancel.mockReset();
  selection.dispose.mockReset();
  drawImage = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.stubGlobal("devicePixelRatio", 1);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("PdfPageCanvas failures", () => {
  it("surfaces a getPage rejection and retries successfully", async () => {
    const { doc, getPage } = makeDoc();
    getPage.mockRejectedValueOnce(new Error("worker unavailable"));
    const onRendered = vi.fn();
    render(<PdfPageCanvas doc={doc} page={1} zoom={1} onRendered={onRendered} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Page 1 could not be rendered");
    expect(console.error).toHaveBeenCalledWith("Could not render PDF page 1", expect.any(Error));
    expect(onRendered).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Retry page" }));
    await waitFor(() => expect(onRendered).toHaveBeenCalledWith(1, { w: 100, h: 200, zoom: 1 }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it.each(["rejection", "synchronous error"])("surfaces a real raster %s", async (mode) => {
    const error = new Error("raster failed");
    const renderPage = vi.fn(() => {
      if (mode === "synchronous error") throw error;
      return { promise: Promise.reject(error), cancel: vi.fn() };
    });
    render(<PdfPageCanvas doc={makeDoc(renderPage).doc} page={1} zoom={1} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Retry this page or reload");
    expect(console.error).toHaveBeenCalledWith("Could not render PDF page 1", error);
  });

  it("keeps expected rendering cancellation quiet", async () => {
    const renderPage = vi.fn(() => ({ promise: Promise.reject(cancellation()), cancel: vi.fn() }));
    render(<PdfPageCanvas doc={makeDoc(renderPage).doc} page={1} zoom={1} />);
    await waitFor(() => expect(renderPage).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByRole("alert")).toBeNull();
    expect(console.error).not.toHaveBeenCalled();
  });

  it("still commits the raster if text selection fails", async () => {
    text.render.mockRejectedValueOnce(new Error("text unavailable"));
    const onRendered = vi.fn();
    render(<PdfPageCanvas doc={makeDoc().doc} page={1} zoom={1} onRendered={onRendered} />);
    await waitFor(() => expect(onRendered).toHaveBeenCalled());
    expect(drawImage).toHaveBeenCalledTimes(1);
    expect(console.warn).toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("text at 100")).toBeNull();
  });
});

describe("PdfPageCanvas render lifecycle", () => {
  it("preserves text layer rotation when committing staged text", async () => {
    const onRendered = vi.fn();
    render(<PdfPageCanvas doc={makeDoc(undefined, 90).doc} page={1} zoom={1} onRendered={onRendered} />);
    await waitFor(() => expect(onRendered).toHaveBeenCalled());
    expect(screen.getByText("text at 100").getAttribute("data-main-rotation")).toBe("90");
  });

  it("waits for cancelled work and commits only the final rapid zoom", async () => {
    const old = task();
    const latest = task();
    const renderPage = vi.fn().mockReturnValueOnce(old).mockReturnValueOnce(latest);
    const { doc } = makeDoc(renderPage);
    const onRendered = vi.fn();
    const view = render(<PdfPageCanvas doc={doc} page={1} zoom={1} onRendered={onRendered} />);
    await waitFor(() => expect(renderPage).toHaveBeenCalledTimes(1));
    view.rerender(<PdfPageCanvas doc={doc} page={1} zoom={3} onRendered={onRendered} />);
    view.rerender(<PdfPageCanvas doc={doc} page={1} zoom={4} onRendered={onRendered} />);
    expect(old.cancel).toHaveBeenCalledTimes(1);
    expect(renderPage).toHaveBeenCalledTimes(1);
    await act(async () => { old.reject(cancellation()); });
    await waitFor(() => expect(renderPage).toHaveBeenCalledTimes(2));
    expect(renderPage.mock.calls[1]![0].viewport.width).toBe(400);
    expect(onRendered).not.toHaveBeenCalled();
    await act(async () => { latest.resolve(); });
    await waitFor(() => expect(onRendered).toHaveBeenCalledTimes(1));
    expect(onRendered).toHaveBeenCalledWith(1, { w: 400, h: 800, zoom: 4 });
    expect((screen.getByTestId("pdf-page-canvas") as HTMLCanvasElement).width).toBe(400);
    expect(screen.getByText("text at 400")).toBeTruthy();
    expect(console.error).not.toHaveBeenCalled();
  });

  it("keeps the previous raster and text intact until the new zoom succeeds", async () => {
    const next = task();
    const renderPage = vi.fn()
      .mockReturnValueOnce({ promise: Promise.resolve(), cancel: vi.fn() })
      .mockReturnValueOnce(next);
    const { doc } = makeDoc(renderPage);
    const onRendered = vi.fn();
    const view = render(<PdfPageCanvas doc={doc} page={1} zoom={1} onRendered={onRendered} />);
    await waitFor(() => expect(onRendered).toHaveBeenCalledTimes(1));
    const visible = screen.getByTestId("pdf-page-canvas") as HTMLCanvasElement;
    expect(renderPage.mock.calls[0]![0].canvas).not.toBe(visible);
    view.rerender(<PdfPageCanvas doc={doc} page={1} zoom={4} onRendered={onRendered} />);
    await waitFor(() => expect(renderPage).toHaveBeenCalledTimes(2));
    expect(visible.width).toBe(100);
    expect(screen.getByText("text at 100")).toBeTruthy();
    expect(selection.dispose).not.toHaveBeenCalled();
    await act(async () => { next.reject(new Error("new zoom failed")); });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(visible.width).toBe(100);
    expect(onRendered).toHaveBeenCalledTimes(1);
    expect(drawImage).toHaveBeenCalledTimes(1);
    expect(selection.dispose).not.toHaveBeenCalled();
    view.unmount();
    expect(selection.dispose).toHaveBeenCalledTimes(1);
  });

  it("cancels stale text work without letting it replace current text", async () => {
    const staleText = deferred();
    text.render.mockReturnValueOnce(staleText.promise);
    const { doc, renderPage } = makeDoc();
    const onRendered = vi.fn();
    const view = render(<PdfPageCanvas doc={doc} page={1} zoom={1} onRendered={onRendered} />);
    await waitFor(() => expect(text.render).toHaveBeenCalledTimes(1));
    view.rerender(<PdfPageCanvas doc={doc} page={1} zoom={4} onRendered={onRendered} />);
    expect(text.cancel).toHaveBeenCalledTimes(1);
    expect(renderPage).toHaveBeenCalledTimes(1);
    await act(async () => { staleText.resolve(); });
    await waitFor(() => expect(onRendered).toHaveBeenCalledTimes(1));
    expect(onRendered).toHaveBeenCalledWith(1, { w: 400, h: 800, zoom: 4 });
    expect(screen.queryByText("text at 100")).toBeNull();
    expect(screen.getByText("text at 400")).toBeTruthy();
  });

  it("cancels on unmount and does not report obsolete errors", async () => {
    const pending = task();
    const renderPage = vi.fn(() => pending);
    const onRendered = vi.fn();
    const view = render(<PdfPageCanvas doc={makeDoc(renderPage).doc} page={1} zoom={1} onRendered={onRendered} />);
    await waitFor(() => expect(renderPage).toHaveBeenCalled());
    view.unmount();
    expect(pending.cancel).toHaveBeenCalledTimes(1);
    await act(async () => { pending.reject(new Error("worker destroyed")); });
    expect(onRendered).not.toHaveBeenCalled();
    expect(console.error).not.toHaveBeenCalled();
  });
});
