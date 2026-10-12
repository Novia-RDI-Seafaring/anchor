import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "/pdf-worker.mjs" }));

afterEach(() => {
  vi.doUnmock("pdfjs-dist");
  vi.resetModules();
});

describe("PDF library loading", () => {
  it("loads the library lazily so module failures reject the document load", async () => {
    const error = new Error("PDF module unsupported in this browser");
    const initialize = vi.fn(() => { throw error; });
    vi.doMock("pdfjs-dist", initialize);
    vi.resetModules();
    const { loadPdf } = await import("./pdfjs");
    expect(initialize).not.toHaveBeenCalled();
    await expect(loadPdf("/document.pdf")).rejects.toThrow();
    expect(initialize).toHaveBeenCalledTimes(1);
  });

  it("destroys a failed worker task and preserves the original load error", async () => {
    const error = new Error("worker failed to boot");
    const destroy = vi.fn(async () => {});
    const GlobalWorkerOptions = { workerSrc: "" };
    const getDocument = vi.fn(() => ({ promise: Promise.reject(error), destroy }));
    vi.doMock("pdfjs-dist", () => ({ GlobalWorkerOptions, getDocument }));
    vi.resetModules();
    const { loadPdf } = await import("./pdfjs");
    await expect(loadPdf("/document.pdf")).rejects.toBe(error);
    expect(GlobalWorkerOptions.workerSrc).toBe("/pdf-worker.mjs");
    expect(destroy).toHaveBeenCalledTimes(1);
  });
});
