/**
 * SelectionPanel — the properties of whatever is selected, open on the left.
 */
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { SelectionPanel } from "./SelectionPanel";

function seed(nodes: Record<string, unknown>) {
  useCanvasStore.setState({ nodes: nodes as never });
}

function renderPanel() {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route path="/canvas/:id" element={<SelectionPanel />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SelectionPanel", () => {
  beforeEach(() => {
    useUiStore.setState({ selectedNodeId: null });
    seed({});
  });

  it("stays out of the way when nothing is selected", () => {
    const { queryByTestId } = renderPanel();
    expect(queryByTestId("selection-panel")).toBeNull();
  });

  it("shows fill, stroke and text for a shape", () => {
    seed({ n1: { id: "n1", node_type: "concept", data: { label: "A" } } });
    useUiStore.setState({ selectedNodeId: "n1" });
    const { getByTestId } = renderPanel();
    const text = getByTestId("selection-panel").textContent ?? "";
    expect(text).toContain("Fill");
    expect(text).toContain("Stroke");
    expect(text).toContain("Text");
  });

  it("shows only text for a text element, which has no box to colour", () => {
    seed({ t1: { id: "t1", node_type: "text", data: { text: "hello" } } });
    useUiStore.setState({ selectedNodeId: "t1" });
    const { getByTestId } = renderPanel();
    const text = getByTestId("selection-panel").textContent ?? "";
    expect(text).toContain("Text");
    expect(text).not.toContain("Fill");
    expect(text).not.toContain("Stroke");
  });
});
