/**
 * FunnelNode render tests — pin the polygon-clipped silhouette and the
 * free-aspect resizing contract.
 *
 * The previous implementation used a `rotate(45deg)` rect which only read
 * as a diamond at a 1:1 aspect ratio; at any stretched size it overflowed
 * into a parallelogram. These tests prevent a regression to that approach
 * by asserting (a) the clip-path polygon is present on the fill div, and
 * (b) the wrapper honours data.width / data.height independently.
 */
import { render } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { FunnelNode } from "./FunnelNode";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Mount = ({ data, selected }: { data: any; selected: boolean }) => (
  <FunnelNode
    {...({
      id: "f1",
      data,
      selected,
      dragging: false,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
      type: "funnel",
      zIndex: 0,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)}
  />
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function renderNode({ data, selected }: { data: any; selected: boolean }) {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route
          path="/canvas/:id"
          element={
            <ReactFlowProvider>
              <Mount data={data} selected={selected} />
            </ReactFlowProvider>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("FunnelNode rendering", () => {
  it("renders the polygon clip-path on the fill layer", () => {
    const { container } = renderNode({
      data: { label: "Decision" },
      selected: false,
    });
    const fill = container.querySelector("div[style*='clip-path']") as HTMLElement | null;
    expect(fill).not.toBeNull();
    expect(fill?.style.clipPath).toContain("polygon");
  });

  it("renders an SVG stroke polygon (free-aspect, non-scaling stroke)", () => {
    const { container } = renderNode({
      data: { label: "Decision" },
      selected: false,
    });
    const polygon = container.querySelector("svg polygon") as SVGPolygonElement | null;
    expect(polygon).not.toBeNull();
    expect(polygon?.getAttribute("points")).toBe("50,0 100,50 50,100 0,50");
    expect(polygon?.getAttribute("vector-effect")).toBe("non-scaling-stroke");
  });

  it("honours non-square width/height (no aspect lock)", () => {
    const { container } = renderNode({
      data: { label: "wide", width: 200, height: 100 },
      selected: false,
    });
    const root = container.firstChild as HTMLElement;
    expect(root.style.width).toBe("200px");
    expect(root.style.height).toBe("100px");
  });

  it("renders the label centred and unrotated", () => {
    const { getByText } = renderNode({
      data: { label: "centred" },
      selected: false,
    });
    const label = getByText("centred");
    expect(label).toBeTruthy();
    // The label container should not carry a rotation transform.
    let el: HTMLElement | null = label;
    while (el) {
      expect(el.style.transform || "").not.toContain("rotate");
      el = el.parentElement;
    }
  });

  it("applies dashed stroke when data.dashed is true", () => {
    const { container } = renderNode({
      data: { label: "soft", dashed: true },
      selected: false,
    });
    const polygon = container.querySelector("svg polygon");
    expect(polygon?.getAttribute("stroke-dasharray")).toBe("6 4");
  });

  it("mounts NodeResizer with free aspect when selected", () => {
    const { container } = renderNode({
      data: { label: "hello" },
      selected: true,
    });
    const handles = container.querySelectorAll(".react-flow__resize-control");
    expect(handles.length).toBeGreaterThan(0);
  });
});
