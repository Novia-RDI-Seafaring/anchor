import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { afterEach, expect, it, vi } from "vitest";

import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { NodeContextToolbar } from "./NodeContextToolbar";

afterEach(cleanup);

it("offers Ask agent for a multi-selection without changing its node selection", () => {
  const selected = ["pump", "limits"];
  const nodes = Object.fromEntries(selected.map((id, index) => [id, {
    id, node_type: "concept", label: id, x: index * 200, y: 0, data: {},
  }]));
  useCanvasStore.setState({ nodes, edges: {} });
  useUiStore.setState({ selectedNodeId: "pump" });
  const onAsk = vi.fn();
  render(<ReactFlowProvider initialNodes={selected.map((id, index) => ({ id, selected: true, position: { x: index * 200, y: 0 }, data: {} }))}>
    <NodeContextToolbar workspaceSlug="study" onAsk={onAsk} />
  </ReactFlowProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Ask agent" }));
  expect(onAsk).toHaveBeenCalledOnce();
  expect(useUiStore.getState().selectedNodeId).toBe("pump");
  expect(Object.keys(useCanvasStore.getState().nodes)).toEqual(selected);
});

function selectOne(node_type: string, data: Record<string, unknown> = {}) {
  useCanvasStore.setState({ nodes: { one: { id: "one", node_type, label: "One", x: 0, y: 0, data } }, edges: {} });
  render(<ReactFlowProvider initialNodes={[{ id: "one", selected: true, position: { x: 0, y: 0 }, data: {} }]}>
    <NodeContextToolbar workspaceSlug="study" onAsk={vi.fn()} />
  </ReactFlowProvider>);
}
const chips = () => ["chip-fill", "chip-stroke", "chip-text", "chip-display"].filter((id) => screen.queryByTestId(id));

it.each([
  ["spec", {}, ["chip-fill", "chip-stroke", "chip-text", "chip-display"]],
  ["concept", {}, ["chip-fill", "chip-stroke", "chip-text", "chip-display"]],
  ["text", {}, ["chip-text"]],
  ["document", { slug: "px" }, []],
  ["image", {}, []],
  ["section", {}, []],
] as const)("shows a single %s only the controls that mean something for it", (type, data, expected) => {
  selectOne(type, data);
  expect(screen.getByTestId("node-context-toolbar")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Ask agent" })).toBeTruthy();
  expect(chips()).toEqual(expected);
});
