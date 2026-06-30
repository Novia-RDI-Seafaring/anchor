/**
 * PageWithBboxViewer value-precise highlight (#197).
 *
 * When the PDF viewer modal is opened for a grounded value, `openPdf` carries
 * the value text as `highlightQuery`. The viewer must locate that text inside
 * the region (documents.locate, scoped to highlightBbox) so it can overlay the
 * value-precise yellow highlight on top of the region rectangle. When no query
 * is present it must NOT locate (region-level highlight only).
 */
import { act, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documents } from "@/api/documents";
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
