/**
 * SelectionPanel — the properties of whatever is selected, open on the left.
 */
import { fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { canvases } from "@/api/canvases";

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

  it("sets a heading through the existing data patch and hides irrelevant box styling", async () => {
    const patch = vi.spyOn(canvases, "patchNode").mockResolvedValue({});
    seed({ n1: { id: "n1", node_type: "concept", data: { source_ref: { slug: "manual", page: 2 } } } });
    useUiStore.setState({ selectedNodeId: "n1" });
    const { getByLabelText, rerender, getByTestId } = renderPanel();
    fireEvent.change(getByLabelText("Node appearance"), { target: { value: "heading" } });
    await waitFor(() => expect(patch).toHaveBeenCalledWith("w1", "n1", { data: { role: "heading" } }));
    seed({ n1: { id: "n1", node_type: "concept", data: { role: "heading" } } });
    rerender(<MemoryRouter initialEntries={["/canvas/w1"]}><Routes><Route path="/canvas/:id" element={<SelectionPanel />} /></Routes></MemoryRouter>);
    expect(getByTestId("selection-panel").textContent).not.toContain("Fill");
    patch.mockRestore();
  });
});
