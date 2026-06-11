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
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useUiStore } from "@/stores/uiStore";

import { TablePrimitive } from "./TablePrimitive";

beforeEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
});

afterEach(() => {
  useUiStore.setState({ hoveredSourceRef: null, pdfViewer: null });
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
    fireEvent.click(screen.getByRole("button", { name: "p2" }));
    expect(useUiStore.getState().pdfViewer).toMatchObject({
      slug: "alfa-laval-lkh",
      page: 2,
      highlightRegionId: "r9",
      highlightPage: 2,
    });
  });
});
