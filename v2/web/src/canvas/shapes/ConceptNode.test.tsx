/**
 * ConceptNode render smoke tests — pin the selection-gated affordances:
 *
 *   - NodeResizer is mounted (rendered) only when the node is selected.
 *   - The inline-edit input does NOT appear on an unselected node, even
 *     after a double-click on the label area (the hook's `canEdit` gate
 *     blocks `beginEdit`).
 *
 * The point isn't to integration-test ReactFlow — just to catch the case
 * where the `selected` prop is accidentally dropped from the renderer or
 * the gate is removed from `useInlineField`.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ConceptNode } from "./ConceptNode";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Mount = ({ selected }: { selected: boolean }) => (
  <ConceptNode
    {...({
      id: "n1",
      data: { label: "hello" },
      selected,
      dragging: false,
      isConnectable: false,
      positionAbsoluteX: 0,
      positionAbsoluteY: 0,
      type: "concept",
      zIndex: 0,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)}
  />
);

function renderNode({ selected }: { selected: boolean }) {
  return render(
    <MemoryRouter initialEntries={["/canvas/w1"]}>
      <Routes>
        <Route
          path="/canvas/:id"
          element={
            <ReactFlowProvider>
              <Mount selected={selected} />
            </ReactFlowProvider>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ConceptNode selection gating", () => {
  it("renders the label", () => {
    renderNode({ selected: false });
    expect(screen.getByText("hello")).toBeTruthy();
  });

  it("does not mount NodeResizer handles when unselected", () => {
    const { container } = renderNode({ selected: false });
    const handles = container.querySelectorAll(".react-flow__resize-control");
    expect(handles.length).toBe(0);
  });

  it("mounts NodeResizer handles when selected", () => {
    const { container } = renderNode({ selected: true });
    const handles = container.querySelectorAll(".react-flow__resize-control");
    // Corner + edge handles — exact count is a ReactFlow detail; just
    // assert >0 to prove the resizer mounted.
    expect(handles.length).toBeGreaterThan(0);
  });

  it("double-click on label does NOT enter edit mode when unselected", () => {
    renderNode({ selected: false });
    const label = screen.getByText("hello");
    fireEvent.doubleClick(label);
    // The edit `<input>` would carry placeholder "label" — absence proves
    // the gate held.
    const input = screen.queryByPlaceholderText("label");
    expect(input).toBeNull();
  });

  it("double-click on label enters edit mode when selected", () => {
    renderNode({ selected: true });
    const label = screen.getByText("hello");
    fireEvent.doubleClick(label);
    const input = screen.queryByPlaceholderText("label");
    expect(input).not.toBeNull();
  });
});
