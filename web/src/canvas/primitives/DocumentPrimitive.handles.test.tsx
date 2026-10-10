import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents, type DocumentIndex, type Region } from "@/api/documents";
import { useUiStore } from "@/stores/uiStore";

import { DocumentPrimitive } from "./DocumentPrimitive";

const refreshInternals = vi.hoisted(() => vi.fn());
vi.mock("@xyflow/react", async (importOriginal) => ({
  ...await importOriginal<typeof import("@xyflow/react")>(),
  useUpdateNodeInternals: () => refreshInternals,
}));

type MeasuredHandle = { id: string | null; top: string; left: string };
let measurements: MeasuredHandle[][];

const index = (generation?: string): DocumentIndex => ({
  document: { filename: "pump.pdf", title: "Pump", page_count: 2,
    ...(generation ? { generation: { id: generation, pages: [1, 2] } } : {}) },
  outline: [],
});
const firstRegion = { id: "first", bbox: [60, 100, 240, 150] };
const secondRegion = { id: "second", bbox: [100, 200, 300, 400] };

function pendingRegions() {
  let resolve!: (regions: Region[]) => void;
  const promise = new Promise<Region[]>((done) => { resolve = done; });
  return { promise, resolve };
}

async function renderDocument() {
  const props: NodeProps = {
    id: "doc1", data: { slug: "pump", status: "ready" }, type: "document",
    selected: false, dragging: false, draggable: true, selectable: true,
    deletable: true, zIndex: 1, isConnectable: true, positionAbsoluteX: 0, positionAbsoluteY: 0,
  };
  await act(async () => {
    render(
      <MemoryRouter>
        <ReactFlowProvider>
          <DocumentPrimitive {...props} />
        </ReactFlowProvider>
      </MemoryRouter>,
    );
  });
}

beforeEach(() => {
  measurements = [];
  refreshInternals.mockReset().mockImplementation(() => {
    // Inspect the committed DOM at measurement time, including removed handles.
    measurements.push([...document.querySelectorAll<HTMLElement>("[data-region-handle-id]")]
      .map((region) => ({ id: region.getAttribute("data-region-handle-id"),
        top: region.style.top, left: region.style.left })));
  });
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
  vi.spyOn(documents, "index").mockResolvedValue(index());
  vi.spyOn(documents, "regions").mockResolvedValue([firstRegion]);
  vi.spyOn(documents, "locate").mockResolvedValue([]);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
    pages_meta: { pages: { "1": { page_size: [600, 800] }, "2": { page_size: [800, 600] } } },
  }) }));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function cachedImage() {
  vi.spyOn(HTMLImageElement.prototype, "complete", "get").mockReturnValue(true);
  vi.spyOn(HTMLImageElement.prototype, "naturalWidth", "get").mockReturnValue(600);
  vi.spyOn(HTMLImageElement.prototype, "naturalHeight", "get").mockReturnValue(800);
}

describe("document region handle registration", () => {
  it.each(["image", "regions"] as const)("registers handles when %s finishes first", async (first) => {
    const pending = pendingRegions();
    vi.mocked(documents.regions).mockReturnValue(pending.promise);
    await renderDocument();
    const image = screen.getByRole("img");
    Object.defineProperties(image, { naturalWidth: { value: 600 }, naturalHeight: { value: 800 } });
    const loadImage = async () => { await act(async () => { fireEvent.load(image); }); };
    const loadRegions = async () => { await act(async () => { pending.resolve([firstRegion]); }); };
    await (first === "image" ? loadImage() : loadRegions());
    expect(document.querySelector("[data-region-handle-id]")).toBeNull();
    await (first === "image" ? loadRegions() : loadImage());
    await waitFor(() => expect(measurements.at(-1)).toEqual([
      { id: "region:first", top: "12.5%", left: "10%" },
    ]));
    expect(refreshInternals).toHaveBeenCalledWith("doc1");
  });

  it("registers a completed cached image without another load event", async () => {
    cachedImage();
    await renderDocument();
    await waitFor(() => expect(measurements.at(-1)?.[0]?.id).toBe("region:first"));
    expect(screen.getByRole("img").getAttribute("src")).toContain("/pages/1/image");
  });

  it("retires the old page's handles while waiting for the new page", async () => {
    cachedImage();
    const pending = pendingRegions();
    vi.mocked(documents.regions).mockImplementation((_slug, page) =>
      page === 2 ? pending.promise : Promise.resolve([firstRegion]));
    await renderDocument();
    await waitFor(() => expect(measurements.at(-1)?.[0]?.id).toBe("region:first"));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "\u203a" })); });
    expect(document.querySelector('[data-region-handle-id="region:first"]')).toBeNull();
    expect(measurements.at(-1)).toEqual([]);
    await act(async () => { pending.resolve([secondRegion]); });
    await waitFor(() => expect(measurements.at(-1)?.[0]?.id).toBe("region:second"));
    expect(parseFloat(measurements.at(-1)![0]!.top)).toBeCloseTo(200 / 600 * 100);
    expect(measurements.at(-1)![0]!.left).toBe("12.5%");
  });

  it("remeasures changed regions on the same page when its generation changes", async () => {
    vi.useFakeTimers();
    cachedImage();
    vi.mocked(documents.index).mockResolvedValueOnce(index("old")).mockResolvedValue(index("new"));
    vi.mocked(documents.regions).mockImplementation(async () => [
      vi.mocked(documents.index).mock.calls.length > 1 ? secondRegion : firstRegion,
    ]);
    await renderDocument();
    expect(measurements.at(-1)?.[0]?.id).toBe("region:first");
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(measurements.at(-1)?.[0]?.id).toBe("region:second");
    expect(document.querySelector('[data-region-handle-id="region:first"]')).toBeNull();
    expect(screen.getByRole("img").getAttribute("src")).toContain("generation=new");
  });
});
