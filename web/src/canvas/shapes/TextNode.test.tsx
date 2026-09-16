/**
 * TextNode — words on the canvas with no card around them.
 */
import { render } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { TextNode } from "./TextNode";

function renderText(data: Record<string, unknown>) {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route
          path="/canvas/:id"
          element={
            <ReactFlowProvider>
              <TextNode
                {...({
                  id: "t1",
                  data,
                  selected: false,
                  dragging: false,
                  isConnectable: false,
                  positionAbsoluteX: 0,
                  positionAbsoluteY: 0,
                  type: "text",
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

describe("TextNode", () => {
  it("renders its text with no border and no background", () => {
    const { getByTestId, getByText } = renderText({ text: "A title" });
    expect(getByText("A title")).toBeTruthy();
    const el = getByTestId("text-node");
    expect(el.style.background).toBe("");
    expect(el.className).not.toContain("border");
  });

  it("renders at the chosen size", () => {
    const { getByTestId } = renderText({ text: "Big", text_size: "3xl" });
    expect(getByTestId("text-node").style.fontSize).toBe("2.5rem");
  });

  it("falls back to the label when no text is set", () => {
    const { getByText } = renderText({ label: "From label" });
    expect(getByText("From label")).toBeTruthy();
  });

  it("takes a width on its own", () => {
    const { getByTestId } = renderText({ text: "Wrapped", width: 420 });
    expect(getByTestId("text-node").style.width).toBe("420px");
  });
});
