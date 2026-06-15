/**
 * ChartPrimitive render tests — pin the generic chart-token contract: one
 * polyline per series, the title, and the provenance chip when a
 * source_ref is present.
 */
import { render, fireEvent } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ChartPrimitive } from "./ChartPrimitive";

const openPdf = vi.fn();
vi.mock("@/stores/uiStore", () => ({
  useUiStore: (sel: (s: unknown) => unknown) =>
    sel({
      openPdf,
      setHoveredSourceRef: vi.fn(),
      clearHoveredSourceRef: vi.fn(),
    }),
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function renderNode(data: any) {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route
          path="/canvas/:id"
          element={
            <ReactFlowProvider>
              <ChartPrimitive
                {...({
                  id: "c1", data, selected: false, dragging: false,
                  isConnectable: false, positionAbsoluteX: 0, positionAbsoluteY: 0,
                  type: "chart", zIndex: 0,
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                } as any)}
              />
            </ReactFlowProvider>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

const CHART = {
  label: "LKH-85 head vs flow",
  chart: {
    x_label: "Q (m3/h)", y_label: "H (m)", x_scale: "linear", y_scale: "linear",
    series: [
      { label: "LKH-85", points: [[0, 94], [150, 94], [300, 80], [400, 50]] },
      { label: "LKH-70", points: [[0, 110], [150, 100], [280, 60]] },
    ],
  },
};

describe("ChartPrimitive rendering", () => {
  it("draws one polyline per series", () => {
    const { container } = renderNode(CHART);
    const lines = container.querySelectorAll("svg polyline");
    expect(lines.length).toBe(2);
    // each polyline has projected points
    expect(lines[0]?.getAttribute("points")).toMatch(/\d+(\.\d+)?,\d+(\.\d+)?/);
  });

  it("shows the title and axis labels", () => {
    const { getByText, container } = renderNode(CHART);
    expect(getByText("LKH-85 head vs flow")).toBeTruthy();
    const texts = [...container.querySelectorAll("svg text")].map((t) => t.textContent);
    expect(texts).toContain("Q (m3/h)");
    expect(texts).toContain("H (m)");
  });

  it("renders the provenance chip and opens the PDF on click", () => {
    const { getByTitle } = renderNode({
      ...CHART,
      source_ref: { kind: "pdf-page-bbox", slug: "lkh-pump", page: 4, bbox: [56, 783, 252, 605] },
    });
    const chip = getByTitle(/Open source · page 4/);
    fireEvent.click(chip);
    expect(openPdf).toHaveBeenCalledWith("lkh-pump", expect.objectContaining({ page: 4 }));
  });

  it("falls back gracefully with no series", () => {
    const { getByText } = renderNode({ label: "Empty", chart: { series: [] } });
    expect(getByText("no series data")).toBeTruthy();
  });
});
