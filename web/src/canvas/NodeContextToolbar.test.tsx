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
