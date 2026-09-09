/**
 * TablePrimitive — row handles + hover behaviour.
 *
 * Two contracts pinned here:
 *  - Every row renders a `data-row-handle-id="row:<i>:<key>"` carrier on
 *    the row's right edge. That id is what an evidence edge wires its
 *    `sourceHandle` to so the floating↔anchored swap finds the right end.
 *  - Hovering a row sets `useUiStore.hoveredSourceRef` to the row's stored
 *    `source_ref` (with `region_id` if present). This drives the doc-node
 *    page-flip + region highlight, and feeds pickEdgeMode.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useUiStore } from "@/stores/uiStore";

import { TablePrimitive } from "./TablePrimitive";

beforeEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
});

afterEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
  vi.unstubAllGlobals();
});

async function renderTable(data: Record<string, unknown>) {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <MemoryRouter initialEntries={["/c/vasa"]}>
        <Routes>
          <Route
            path="/c/:id"
            element={
              <ReactFlowProvider>
                <TablePrimitive
                  {...({
                    id: "spec1",
                    data,
                    selected: false,
                    dragging: false,
                    isConnectable: true,
                    positionAbsoluteX: 0,
                    positionAbsoluteY: 0,
                    type: "spec",
                    zIndex: 0,
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  } as any)}
                />
              </ReactFlowProvider>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
  });
  return result;
}

describe("TablePrimitive row handles", () => {
  it("renders a row-handle carrier on every row, ids encoding the row key", async () => {
    await renderTable({
      label: "Operating limits (LKH-5)",
      source_doc_slug: "alfa-laval-lkh-centrifugal-pump",
      source_region_id: "r4",
      source_ref: { page: 2, bbox: [55.4, 477.1, 552.9, 411.0] },
      rows: [
        { key: "Max inlet pressure", value: "600 kPa", source_ref: { page: 2, region_id: "r4" } },
        { key: "Temperature range", value: "-10 to 140", source_ref: { page: 2 } },
      ],
    });
    const rows = screen.getAllByRole("row");
    // jsdom counts both <tr>; both should have our data attribute.
    const ids = rows.map((r) => r.getAttribute("data-row-handle-id"));
    expect(ids).toEqual([
      "row:0:Max inlet pressure",
      "row:1:Temperature range",
    ]);
  });

  it("broadcasts the row's own source_ref (with region_id) on row hover", async () => {
    await renderTable({
      label: "Operating limits (LKH-5)",
      source_doc_slug: "alfa-laval-lkh-centrifugal-pump",
      source_region_id: "r4",
      source_ref: { page: 2, bbox: [55.4, 477.1, 552.9, 411.0] },
      rows: [
        {
          key: "Max inlet pressure",
          value: "600 kPa",
          source_ref: { page: 2, region_id: "r4", bbox: [55.4, 477.1, 552.9, 411.0] },
        },
      ],
    });
    const row = screen.getByText("Max inlet pressure").closest("tr");
    expect(row).not.toBeNull();
    await act(async () => {
      fireEvent.mouseEnter(row!);
    });
    const hovered = useUiStore.getState().hoveredSourceRef;
    expect(hovered).not.toBeNull();
    expect(hovered!.slug).toBe("alfa-laval-lkh-centrifugal-pump");
    expect(hovered!.page).toBe(2);
    expect(hovered!.region_id).toBe("r4");
  });

  it("falls back to the spec's node-level source_ref when a row has none of its own", async () => {
    await renderTable({
      label: "Spec without per-row refs",
      source_doc_slug: "lkh",
      source_region_id: "r9",
      source_ref: { page: 3, bbox: [1, 2, 3, 4] },
      rows: [{ key: "k", value: "v" }],
    });
    const row = screen.getByText("k").closest("tr");
    await act(async () => {
      fireEvent.mouseEnter(row!);
    });
    const hovered = useUiStore.getState().hoveredSourceRef;
    expect(hovered).not.toBeNull();
    expect(hovered!.page).toBe(3);
    expect(hovered!.region_id).toBe("r9");
  });

  it("uses the row source slug when the spec has no node-level source document", async () => {
    await renderTable({
      label: "Spec-Config",
      rows: [
        {
          key: "min temp",
          value: "-10 C",
          source_ref: { slug: "alfa-laval-lkh", page: 2, region_id: "r9" },
        },
      ],
    });
    const row = screen.getByText("min temp").closest("tr");
    await act(async () => {
      fireEvent.mouseEnter(row!);
    });
    expect(useUiStore.getState().hoveredSourceRef).toEqual({
      slug: "alfa-laval-lkh",
      page: 2,
      region_id: "r9",
      bbox: undefined,
      // The hover now carries the cell value so the document node can draw the
      // value-precise highlight (#197).
      query: "-10 C",
    });
  });

  it("opens the row source page and region when the row page button is clicked", async () => {
    await renderTable({
      label: "Spec-Config",
      rows: [
        {
          key: "min temp",
          value: "-10 C",
          source_ref: { slug: "alfa-laval-lkh", page: 2, region_id: "r9" },
        },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "Open source page 2" }));
    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: "alfa-laval-lkh",
      page: 2,
      highlightRegionId: "r9",
      highlightPage: 2,
    });
  });

  it("uses a rendered bbox crop for dragged-region previews", async () => {
    await renderTable({
      label: "Dragged region",
      source_doc_slug: "doc-a",
      source_region_id: "region-a",
      source_ref: { page: 3, bbox: [1, 2, 3, 4] },
      crops: { png: "3/region-a-custom.png" },
      description: "Region summary",
    });

    expect(screen.getByAltText("Dragged region").getAttribute("src")).toBe(
      "/api/documents/doc-a/pages/3/crop?bbox=1%2C2%2C3%2C4&dpi=300",
    );
  });

  it("uses the stored region crop when no bbox exists", async () => {
    await renderTable({
      label: "Dragged region",
      source_doc_slug: "doc-a",
      source_region_id: "region-a",
      source_ref: { page: 3 },
      crops: { png: "3/region-a-custom.png" },
      description: "Region summary",
    });

    expect(screen.getByAltText("Dragged region").getAttribute("src")).toBe(
      "/api/documents/doc-a/crops/3/region-a-custom.png",
    );
  });

  it("uses a rendered bbox crop when no stored crop exists", async () => {
    await renderTable({
      label: "Dragged region without crop",
      source_doc_slug: "doc-b",
      source_region_id: "region-b",
      source_ref: {
        page: 4,
        bbox: [10, 20, 110, 70],
      },
      description: "Region summary",
    });

    expect(screen.getByAltText("Dragged region without crop").getAttribute("src")).toBe(
      "/api/documents/doc-b/pages/4/crop?bbox=10%2C20%2C110%2C70&dpi=300",
    );
  });

  it("marks a grounded value for the yellow hover highlight; leaves an ungrounded value plain", async () => {
    await renderTable({
      label: "Mixed grounding",
      source_doc_slug: "lkh",
      rows: [
        { key: "Grounded", value: "600 kPa", source_ref: { page: 2, region_id: "r4" } },
        { key: "Plain", value: "no source" },
      ],
    });
    // The grounded value carries the marker affordance with the yellow
    // on-hover class; the ungrounded value does not get the marker.
    const markers = screen.getAllByTestId("spec-value-marker");
    expect(markers).toHaveLength(1);
    expect(markers[0]!.textContent).toBe("600 kPa");
    expect(markers[0]!.className).toContain("group-hover/tr:bg-yellow-200");
    expect(screen.getByText("no source").getAttribute("data-testid")).toBeNull();
  });

  // --- #242 P2c: highlight through the resolver (closes #274) -------------

  it("opens a selector-less ref with its own bbox and never calls the resolver", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await renderTable({
      label: "Spec-Config",
      rows: [
        {
          key: "min temp",
          value: "-10 C",
          source_ref: { slug: "alfa-laval-lkh", page: 2, region_id: "r9", bbox: [50, 40, 550, 200] },
        },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "Open source page 2" }));
    // Synchronous, region-level path — unchanged by P2c.
    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: "alfa-laval-lkh",
      page: 2,
      highlightRegionId: "r9",
      highlightBbox: [50, 40, 550, 200],
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("resolves a cell-selector ref via resolve-ref and highlights the cell bbox", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        slug: "alfa-laval-lkh",
        page: 2,
        bbox: [280, 120, 340, 132],
        precision: "cell",
        region_id: "r4",
        cell: { row: 0, col: 1 },
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    await renderTable({
      label: "Spec-Config",
      rows: [
        {
          key: "Flow",
          value: "35 m3/h",
          source_ref: {
            slug: "alfa-laval-lkh",
            page: 2,
            region_id: "r4",
            bbox: [50, 40, 550, 200],
            cell: { row: 0, col: 1 },
          },
        },
      ],
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open source page 2" }));
    });
    const url = (fetchMock.mock.calls[0] as unknown[] | undefined)?.[0] as string ?? "";
    expect(url).toContain("/api/documents/alfa-laval-lkh/resolve-ref");
    expect(url).toContain("row=0");
    expect(url).toContain("col=1");
    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: "alfa-laval-lkh",
      page: 2,
      highlightRegionId: "r4",
      highlightBbox: [280, 120, 340, 132],
    });
  });

  it("falls back to the ref's own bbox when the resolver answers 404", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false,
      status: 404,
      text: async () => "unresolvable ref",
    })));
    await renderTable({
      label: "Spec-Config",
      rows: [
        {
          key: "Flow",
          value: "35 m3/h",
          source_ref: {
            slug: "alfa-laval-lkh",
            page: 2,
            region_id: "r4",
            bbox: [50, 40, 550, 200],
            cell: { row: 0, col: 1 },
          },
        },
      ],
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open source page 2" }));
    });
    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: "alfa-laval-lkh",
      page: 2,
      highlightBbox: [50, 40, 550, 200],
    });
  });
});
