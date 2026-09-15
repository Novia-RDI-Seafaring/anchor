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

import { canvases } from "@/api/canvases";
import { useUiStore } from "@/stores/uiStore";

import { TablePrimitive } from "./TablePrimitive";

beforeEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
});

afterEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
});

async function renderTable(data: Record<string, unknown>, selected = false) {
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
                    selected,
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
  it("labels a historical source as unverified, not grounded", async () => {
    await renderTable({ rows: [{ key: "Pressure", value: "42", source_ref: { page: 1 } }] });
    expect(screen.queryByTestId("spec-value-marker")).toBeNull();
    expect(screen.getByText("Unverified")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open source page 1" })).toBeTruthy();
  });
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
        { key: "Grounded", value: "600 kPa", source_ref: { page: 2, region_id: "r4" }, evidence: {
          status: "verified", claim: { key: "grounded", value: "600 kPa" },
          source_ref: { page: 2, region_id: "r4" }, validation: { producer: "anchor_pdfs" },
        } },
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

  it("shows all evidence states with text and keeps stale citations clickable", async () => {
    const source_ref = { slug: "doc", page: 1, region_id: "pressure" };
    const evidence = { status: "verified", claim: { key: "pressure", value: "42" },
      source_ref, validation: { producer: "anchor_pdfs" } };
    await renderTable({ rows: [
      { key: "Pressure", value: "42", source_ref, evidence },
      { key: "Pressure", value: "999999", source_ref, evidence },
      { key: "Historical", value: "21", source_ref },
      { key: "Unfilled", value: "" },
    ] });
    for (const label of ["Verified", "Stale", "Unverified", "No evidence"]) {
      expect(screen.getByLabelText(`Evidence: ${label}`)).toBeTruthy();
    }
    expect(screen.getAllByTestId("spec-value-marker")).toHaveLength(1);
    fireEvent.click(screen.getAllByRole("button", { name: "Open source page 1" })[1]!);
    expect(useUiStore.getState().pdfViewer).toMatchObject({ slug: "doc", page: 1 });
  });

  it("removes verified presentation immediately on edit and requests deliberate revalidation", async () => {
    const patch = vi.spyOn(canvases, "patchNode").mockResolvedValue({} as never);
    const source_ref = { slug: "doc", page: 1 };
    await renderTable({ rows: [{ key: "Pressure", value: "42", source_ref,
      evidence: { status: "verified", claim: { key: "pressure", value: "42" },
        source_ref, validation: { producer: "anchor_pdfs" } },
    }] }, true);
    fireEvent.click(screen.getByText("42"));
    fireEvent.change(screen.getByPlaceholderText("value"), { target: { value: "999999" } });
    fireEvent.blur(screen.getByPlaceholderText("value"));
    expect(screen.getByText("Stale")).toBeTruthy();
    expect(screen.queryByTestId("spec-value-marker")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Revalidate evidence for Pressure" }));
    expect(patch.mock.lastCall?.[2].data).toMatchObject({ rows: [{
      key: "Pressure", value: "999999", source_ref, revalidate_evidence: true,
    }] });
    patch.mockRestore();
  });
});
