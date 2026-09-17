/**
 * AreaNode title sizing.
 *
 * A region's title is the heading of whatever it holds. It used to be
 * pinned at 10px, so a canvas composed of labelled regions and read zoomed
 * out had headings nobody could read.
 */
import { render } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AreaNode } from "./AreaNode";

function renderArea(data: Record<string, unknown>) {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route
          path="/canvas/:id"
          element={
            <ReactFlowProvider>
              <AreaNode
                {...({
                  id: "a1",
                  data,
                  selected: false,
                  dragging: false,
                  isConnectable: false,
                  positionAbsoluteX: 0,
                  positionAbsoluteY: 0,
                  type: "area",
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
}

describe("AreaNode title", () => {
  it("keeps the small default when no size is set", () => {
    const { container } = renderArea({ label: "Core domain" });
    const title = container.querySelector(".uppercase") as HTMLElement;
    expect(title.style.fontSize).toBe("0.6875rem");
  });

  it("grows with the region's text size", () => {
    const { container } = renderArea({ label: "Core domain", text_size: "2xl" });
    const title = container.querySelector(".uppercase") as HTMLElement;
    expect(title.style.fontSize).toBe("1.375rem");
  });

  it("scales the subtitle with the title", () => {
    const { container } = renderArea({
      label: "Core domain",
      subtitle: "pure python",
      text_size: "xl",
    });
    const subtitle = container.querySelector(".italic") as HTMLElement;
    // jsdom folds the multiplication; the point is that it tracks the title.
    expect(subtitle.style.fontSize).toBe("calc(0.85rem)");
  });
});
