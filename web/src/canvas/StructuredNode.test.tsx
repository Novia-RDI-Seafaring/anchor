import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { CanvasStructureContext, structuredNodeTypes } from "./StructuredNode";
import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

const Full = ({ data }: NodeProps) => <p>{String(data.text)}</p>;
const Renderer = structuredNodeTypes({ fact: Full }).fact!;
const props = (data: Record<string, unknown>, type = "fact"): NodeProps => ({
  id: "n1", data, type, selected: true, dragging: false, isConnectable: false,
  positionAbsoluteX: 0, positionAbsoluteY: 0, zIndex: 0,
  draggable: true, selectable: true, deletable: true,
});

it("shows a compact first line, fold count and detail action while full mode preserves content", () => {
  const toggle = vi.fn();
  const inspect = vi.fn();
  const context = { counts: new Map([["n1", 4]]), toggle, inspect };
  const mount = (data: Record<string, unknown>) => <MemoryRouter><ReactFlowProvider>
    <CanvasStructureContext.Provider value={context}><Renderer {...props(data)} /></CanvasStructureContext.Provider>
  </ReactFlowProvider></MemoryRouter>;
  const { rerender } = render(mount({ label: "Limit", text: "Short line\nLong second line", collapsed: true }));
  expect(screen.getByText("Short line")).toBeTruthy();
  expect(screen.queryByText(/Long second line/)).toBeNull();
  expect(screen.getByRole("button", { name: "Expand subtree" }).textContent).toBe("+4");
  fireEvent.click(screen.getByRole("button", { name: "Expand subtree" }));
  expect(toggle).toHaveBeenCalledWith("n1");
  fireEvent.doubleClick(screen.getByText("Short line"));
  expect(inspect).toHaveBeenCalledWith("n1");
  rerender(mount({ text: "Short line\nLong second line", display_mode: "full" }));
  expect(screen.getByText(/Long second line/)).toBeTruthy();
});

it("tolerates arbitrary table rows while retaining row handles", () => {
  const { container } = render(<MemoryRouter><ReactFlowProvider><Renderer {...props({ label: "Data", rows: [null, 12, { key: "Speed" }] }, "spec")} /></ReactFlowProvider></MemoryRouter>);
  expect(screen.getByText("3 rows")).toBeTruthy();
  expect(container.querySelector('[data-handleid="row:2:Speed"]')).toBeTruthy();
});

it("allows inspection in a read-only view without fold or edit controls", () => {
  const inspect = vi.fn();
  render(<MemoryRouter><ReactFlowProvider><CanvasStructureContext.Provider value={{ counts: new Map([["n1", 3]]), readOnly: true, inspect, toggle: vi.fn() }}>
    <Renderer {...props({ text: "Short line" })} />
  </CanvasStructureContext.Provider></ReactFlowProvider></MemoryRouter>);
  fireEvent.doubleClick(screen.getByText("Short line"));
  expect(inspect).toHaveBeenCalledWith("n1");
  expect(screen.queryByRole("button", { name: /subtree/ })).toBeNull();
});

it("preserves pending inline rename on a newly placed compact card", async () => {
  const patch = vi.spyOn(canvases, "patchNode").mockResolvedValue({});
  useCanvasStore.setState({ nodes: { n1: { id: "n1", node_type: "fact", label: "", x: 0, y: 0, data: {} } } });
  useUiStore.getState().requestInlineRename("n1");
  render(<MemoryRouter><ReactFlowProvider><Renderer {...props({ label: "" })} /></ReactFlowProvider></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Node label" })).toBeTruthy());
  fireEvent.change(screen.getByRole("textbox", { name: "Node label" }), { target: { value: "New claim" } });
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Node label" }), { key: "Enter" });
  patch.mockRestore();
});

it("keeps document and sub-canvas double-click actions available without also inspecting", () => {
  const inspect = vi.fn();
  const Special = structuredNodeTypes({ document: Full }).document!;
  render(<MemoryRouter><ReactFlowProvider><CanvasStructureContext.Provider value={{ counts: new Map(), inspect, toggle: vi.fn() }}>
    <Special {...props({ text: "Document content", display_mode: "full" }, "document")} />
  </CanvasStructureContext.Provider></ReactFlowProvider></MemoryRouter>);
  fireEvent.doubleClick(screen.getByText("Document content"));
  expect(inspect).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Details" }));
  expect(inspect).toHaveBeenCalledWith("n1");
});
