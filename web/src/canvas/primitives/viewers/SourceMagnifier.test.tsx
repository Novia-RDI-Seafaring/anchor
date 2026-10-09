import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourceMagnifier } from "./SourceMagnifier";
import type { PdfDoc } from "./pdfjs";

function deferred() {
  let resolve!: () => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<void>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function fakeDoc() {
  const draws: { canvas: HTMLCanvasElement; viewport: { width: number; height: number }; transform: number[] }[] = [];
  const completions: ReturnType<typeof deferred>[] = [];
  const cancel = vi.fn();
  const pdfPage = {
    getViewport: vi.fn(({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale })),
    render: vi.fn((options: typeof draws[number]) => {
      draws.push(options);
      const completion = deferred();
      completions.push(completion);
      return { promise: completion.promise, cancel };
    }),
  };
  const getPage = vi.fn(async () => pdfPage);
  return { doc: { numPages: 2, getPage } as unknown as PdfDoc, pdfPage, getPage, draws, completions, cancel };
}

function geometry() {
  const scroller = document.createElement("div");
  Object.defineProperties(scroller, { clientWidth: { value: 640 }, clientHeight: { value: 600 } });
  const content = document.createElement("div");
  return {
    scroller,
    contentRef: { current: content }, scrollRef: { current: scroller },
    pageRect: { left: 0, top: 0, width: 600, height: 800 },
    sourceRect: { left: 100, top: 100, width: 20, height: 20 },
  };
}

async function settle() {
  await act(async () => { await vi.advanceTimersByTimeAsync(120); });
}

let drawImage: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("devicePixelRatio", 2);
  drawImage = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SourceMagnifier rendering", () => {
  it("renders only a crisp bounded crop and commits it after success", async () => {
    const pdf = fakeDoc();
    const refs = geometry();
    render(<SourceMagnifier doc={pdf.doc} page={1} bbox={[100, 100, 120, 120]}
      zoom={1} pageSize={{ w: 600, h: 800 }} {...refs} />);
    const lens = screen.getByTestId("source-magnifier");
    const canvas = lens.querySelector("canvas")!;
    expect(lens.style.pointerEvents).toBe("none");
    expect(lens.style.userSelect).toBe("none");
    expect(canvas.style.visibility).toBe("hidden");
    await settle();
    expect(pdf.pdfPage.getViewport).toHaveBeenCalledWith({ scale: 2.5 });
    expect(pdf.draws[0]!.canvas).not.toBe(canvas);
    expect([pdf.draws[0]!.canvas.width, pdf.draws[0]!.canvas.height]).toEqual([440, 224]);
    expect(pdf.draws[0]!.transform).toEqual([2, 0, 0, 2, -330, -438]);
    expect(drawImage).not.toHaveBeenCalled();
    await act(async () => { pdf.completions[0]!.resolve(); });
    expect(drawImage).toHaveBeenCalledOnce();
    expect([canvas.width, canvas.height]).toEqual([440, 224]);
    expect(canvas.style.visibility).toBe("visible");
    expect(pdf.draws[0]!.canvas.width).toBe(0);
  });

  it("cancels a superseded crop and never commits its late completion", async () => {
    const pdf = fakeDoc();
    const refs = geometry();
    const view = (bbox: number[]) => <SourceMagnifier doc={pdf.doc} page={1} bbox={bbox}
      zoom={1} pageSize={{ w: 600, h: 800 }} {...refs} />;
    const { rerender } = render(view([100, 100, 120, 120]));
    await settle();
    rerender(view([200, 100, 220, 120]));
    expect(pdf.cancel).toHaveBeenCalledOnce();
    await act(async () => { pdf.completions[0]!.resolve(); });
    expect(drawImage).not.toHaveBeenCalled();
    await settle();
    await act(async () => { pdf.completions[1]!.resolve(); });
    expect(drawImage).toHaveBeenCalledOnce();
    expect(screen.getByTestId("source-magnifier").querySelector("canvas")!.style.visibility).toBe("visible");
  });

  it("hides the old document crop immediately and caps device pixels", async () => {
    const first = fakeDoc();
    const next = fakeDoc();
    const refs = geometry();
    const view = (doc: PdfDoc) => <SourceMagnifier doc={doc} page={1} bbox={[100, 100, 120, 120]}
      zoom={0.5} pageSize={{ w: 600, h: 800 }} {...refs} />;
    const { rerender } = render(view(first.doc));
    await settle();
    await act(async () => { first.completions[0]!.resolve(); });
    expect(screen.getByTestId("source-magnifier").querySelector("canvas")!.style.visibility).toBe("visible");
    vi.stubGlobal("devicePixelRatio", 5);
    rerender(view(next.doc));
    expect(screen.getByTestId("source-magnifier").querySelector("canvas")!.style.visibility).toBe("hidden");
    await settle();
    expect(next.pdfPage.getViewport).toHaveBeenCalledWith({ scale: 1.25 });
    expect([next.draws[0]!.canvas.width, next.draws[0]!.canvas.height]).toEqual([660, 336]);
    await act(async () => { next.completions[0]!.resolve(); });
  });

  it("debounces short-lived highlights and cancels on dismissal", async () => {
    const pdf = fakeDoc();
    const refs = geometry();
    const props = { doc: pdf.doc, page: 1, bbox: [100, 100, 120, 120], zoom: 1,
      pageSize: { w: 600, h: 800 }, ...refs };
    const transient = render(<SourceMagnifier {...props} />);
    transient.unmount();
    await settle();
    expect(pdf.getPage).not.toHaveBeenCalled();
    const visible = render(<SourceMagnifier {...props} />);
    await settle();
    visible.unmount();
    expect(pdf.cancel).toHaveBeenCalledOnce();
    await act(async () => { pdf.completions[0]!.resolve(); });
    expect(drawImage).not.toHaveBeenCalled();
  });

  it("removes the lens offscreen and renders a fresh crop when it returns", async () => {
    const pdf = fakeDoc();
    const refs = geometry();
    render(<SourceMagnifier doc={pdf.doc} page={1} bbox={[100, 100, 120, 120]}
      zoom={1} pageSize={{ w: 600, h: 800 }} {...refs} />);
    expect(screen.getByTestId("source-magnifier")).toBeTruthy();
    await settle();
    await act(async () => { pdf.completions[0]!.resolve(); });
    refs.scroller.scrollTop = 500;
    fireEvent.scroll(refs.scroller);
    expect(screen.queryByTestId("source-magnifier")).toBeNull();
    await settle();
    expect(pdf.getPage).toHaveBeenCalledOnce();
    refs.scroller.scrollTop = 0;
    fireEvent.scroll(refs.scroller);
    expect(screen.getByTestId("source-magnifier").querySelector("canvas")!.style.visibility).toBe("hidden");
    await settle();
    await act(async () => { pdf.completions[1]!.resolve(); });
    expect(screen.getByTestId("source-magnifier").querySelector("canvas")!.style.visibility).toBe("visible");
  });

  it("shows an unavailable state without committing a failed render", async () => {
    const pdf = fakeDoc();
    render(<SourceMagnifier doc={pdf.doc} page={1} bbox={[100, 100, 120, 120]}
      zoom={1} pageSize={{ w: 600, h: 800 }} {...geometry()} />);
    await settle();
    await act(async () => { pdf.completions[0]!.reject(new Error("PDF render failed")); });
    expect(screen.getByText("Magnifier unavailable")).toBeTruthy();
    expect(drawImage).not.toHaveBeenCalled();
    expect(screen.getByTestId("source-magnifier").querySelector("canvas")!.style.visibility).toBe("hidden");
  });
});
