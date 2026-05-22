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

/**
 * Style picker smoke — proves `data.bg_color` and `data.stroke_color`
 * actually reach the rendered inline style. Catches the case where the
 * resolveColors() call is dropped or the inline style override is removed
 * by mistake.
 */
describe("ConceptNode Style picker", () => {
  function renderWithColors(bg?: string, stroke?: string) {
    return render(
      <MemoryRouter initialEntries={["/canvas/w1"]}>
        <Routes>
          <Route
            path="/canvas/:id"
            element={
              <ReactFlowProvider>
                <ConceptNode
                  {...({
                    id: "n1",
                    data: { label: "tint", bg_color: bg, stroke_color: stroke },
                    selected: false,
                    dragging: false,
                    isConnectable: false,
                    positionAbsoluteX: 0,
                    positionAbsoluteY: 0,
                    type: "concept",
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

  it("applies data.bg_color to the wrapper background", () => {
    const { container } = renderWithColors("#fef3c7");
    const wrapper = container.firstChild as HTMLElement;
    // jsdom normalises hex to rgb when setting via inline style — assert
    // the normalised form. #fef3c7 == rgb(254, 243, 199).
    expect(wrapper.style.background).toBe("rgb(254, 243, 199)");
  });

  it("applies data.stroke_color to borderColor and color", () => {
    const { container } = renderWithColors(undefined, "rgb(202, 138, 4)");
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.borderColor).toBe("rgb(202, 138, 4)");
    expect(wrapper.style.color).toBe("rgb(202, 138, 4)");
  });
});

/**
 * Text picker smoke — proves `data.text_*` fields actually reach the label
 * element's inline style. Catches the case where the resolveText() call is
 * removed from ConceptNode by mistake.
 */
describe("ConceptNode Text picker", () => {
  function renderWithText(data: Record<string, unknown>) {
    return render(
      <MemoryRouter initialEntries={["/canvas/w1"]}>
        <Routes>
          <Route
            path="/canvas/:id"
            element={
              <ReactFlowProvider>
                <ConceptNode
                  {...({
                    id: "n1",
                    data: { label: "tint", ...data },
                    selected: false,
                    dragging: false,
                    isConnectable: false,
                    positionAbsoluteX: 0,
                    positionAbsoluteY: 0,
                    type: "concept",
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

  it("applies text_bold + text_align to the label", () => {
    const { getByText } = renderWithText({ text_bold: true, text_align: "center" });
    const label = getByText("tint") as HTMLElement;
    expect(label.style.fontWeight).toBe("700");
    expect(label.style.textAlign).toBe("center");
  });

  it("applies text_size 'lg' as 1rem", () => {
    const { getByText } = renderWithText({ text_size: "lg" });
    const label = getByText("tint") as HTMLElement;
    expect(label.style.fontSize).toBe("1rem");
  });
});
