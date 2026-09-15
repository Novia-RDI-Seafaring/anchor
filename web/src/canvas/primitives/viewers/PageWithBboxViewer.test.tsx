/**
 * PageWithBboxViewer value-precise highlight (#197).
 *
 * When the PDF viewer modal is opened for a grounded value, `openPdf` carries
 * the value text as `highlightQuery`. The viewer must locate that text inside
 * the region (documents.locate, scoped to highlightBbox) so it can overlay the
 * value-precise yellow highlight on top of the region rectangle. When no query
 * is present it must NOT locate (region-level highlight only).
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
import fixture from "@/lib/fixtures/documentPageGeometry.json";
import { useUiStore } from "@/stores/uiStore";

import { PageWithBboxViewer } from "./PageWithBboxViewer";

beforeEach(() => {
  useUiStore.setState({ pdfViewer: null });
  vi.spyOn(documents, "index").mockResolvedValue({
    document: { page_count: 3 },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.spyOn(documents, "regions").mockResolvedValue([]);
  vi.spyOn(documents, "locate").mockResolvedValue([]);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => null }),
  );
});

afterEach(() => {
  vi.useRealTimers();
  useUiStore.setState({ pdfViewer: null });
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function renderViewer() {
  await act(async () => {
    render(
      <MemoryRouter>
        <PageWithBboxViewer />
      </MemoryRouter>,
    );
  });
}

describe("PageWithBboxViewer value-precise highlight", () => {
  it("refreshes a removed real-datasheet page in an already-open modal", async () => {
    vi.useFakeTimers();
    await renderViewer();
    await act(async () => { useUiStore.getState().openPdf("alfa-laval-lkh", { page: 2, mode: "modal" }); });
    expect(screen.getByText("2 / 3")).toBeTruthy();
    vi.mocked(documents.index).mockResolvedValue({ document: { page_count: 1, title: "Alfa Laval LKH", filename: "Alfa Laval LKH.pdf",
      generation: { id: "replacement-b", pages: [1] } }, outline: [] } as Awaited<ReturnType<typeof documents.index>>);
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(screen.getByText("1 / 1")).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("src")).toContain("generation=replacement-b");
  });

  it("locates the value text scoped to the region bbox when opened for a value", async () => {
    await renderViewer();
    await act(async () => {
      useUiStore.getState().openPdf("alfa-laval-lkh", {
        page: 2,
        mode: "modal",
        highlightRegionId: "r9",
        highlightBbox: [50, 480, 550, 410],
        highlightQuery: "600 kPa",
      });
    });
    expect(documents.locate).toHaveBeenCalledWith(
      "alfa-laval-lkh",
      2,
      "600 kPa",
      [50, 480, 550, 410],
    );
  });

  it("does not locate when opened without a value query (region-only)", async () => {
    await renderViewer();
    await act(async () => {
      useUiStore.getState().openPdf("alfa-laval-lkh", {
        page: 2,
        mode: "modal",
        highlightRegionId: "r9",
        highlightBbox: [50, 480, 550, 410],
      });
    });
    expect(documents.locate).not.toHaveBeenCalled();
  });
});

it.each(["72", "150", "300"] as const)("uses declared page points with a %s-DPI modal raster", async (dpi) => {
  vi.spyOn(documents, "index").mockResolvedValue({ document: fixture.gold_map.document, outline: [] });
  vi.spyOn(documents, "regions").mockResolvedValue(fixture.gold_map.pages["1"]);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fixture.gold_map }));
  useUiStore.getState().openPdf("geometry", { page: 1, mode: "modal" });
  let container!: HTMLElement;
  await act(async () => { container = render(<PageWithBboxViewer />).container; });
  const image = screen.getByRole("img") as HTMLImageElement;
  const raster = fixture.rasters[dpi]["1"];
  Object.defineProperties(image, { naturalWidth: { value: raster.width }, naturalHeight: { value: raster.height } });
  await act(async () => { fireEvent.load(image); });
  const rect = container.querySelector("rect")!;
  expect(Number(rect.getAttribute("x")) / raster.width).toBeCloseTo(0.1, 12);
  expect(Number(rect.getAttribute("y")) / raster.height).toBeCloseTo(0.125, 12);
  expect(Number(rect.getAttribute("width")) / raster.width).toBeCloseTo(0.3, 12);
  expect(Number(rect.getAttribute("height")) / raster.height).toBeCloseTo(0.0625, 12);
});

it("keeps the modal image and region list when precise geometry is unknown", async () => {
  vi.mocked(documents.regions).mockResolvedValue(fixture.gold_map.pages["1"]);
  useUiStore.getState().openPdf("geometry", { page: 1, mode: "modal" });
  let container!: HTMLElement;
  await act(async () => { container = render(<PageWithBboxViewer />).container; });
  const image = screen.getByRole("img") as HTMLImageElement;
  Object.defineProperties(image, { naturalWidth: { value: 600 }, naturalHeight: { value: 800 } });
  await act(async () => { fireEvent.load(image); });
  expect(container.querySelector("svg")).toBeNull();
  expect(screen.getByRole("status").textContent).toContain("page dimensions unknown");
  expect(screen.getByRole("button", { name: "review text" })).toBeTruthy();
  expect(image.getAttribute("src")).toContain("/pages/1/image");
});
