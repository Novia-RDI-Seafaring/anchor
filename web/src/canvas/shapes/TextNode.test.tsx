/**
 * TextNode — words on the canvas with no card around them.
 */
import { act, render } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useUiStore } from "@/stores/uiStore";

import { TextNode } from "./TextNode";

function renderText(data: Record<string, unknown>, selected = false) {
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
                  selected,
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

  it("hugs its words when no width is set", () => {
    // The selection box is the element's box. A stored default width left a
    // short word sitting inside a very wide frame.
    const { getByTestId } = renderText({ text: "sdfsdf" });
    expect(getByTestId("text-node").style.width).toBe("max-content");
  });

  it("takes a width when one is set, to wrap a paragraph at a measure", () => {
    const { getByTestId } = renderText({ text: "Wrapped", width: 420 });
    expect(getByTestId("text-node").style.width).toBe("420px");
  });
});

describe("TextNode editing", () => {
  it("opens its editor when a freshly placed element asks for focus", async () => {
    // Placing a text element stamps its id for focus. A text element has no
    // label, so its body claims that stamp: place it and type.
    useUiStore.setState({ pendingInlineRenameNodeId: "t1" });
    const { container } = renderText({ text: "" }, true);
    await act(async () => {});
    expect(container.querySelector("textarea")).toBeTruthy();
  });

  it("edits in place: no box around the words", async () => {
    useUiStore.setState({ pendingInlineRenameNodeId: "t1" });
    const { container } = renderText({ text: "hi", text_size: "xl" }, true);
    await act(async () => {});
    const ta = container.querySelector("textarea") as HTMLTextAreaElement;
    expect(ta.className).toContain("border-0");
    expect(ta.className).toContain("bg-transparent");
    // Same size as the rendered words, so nothing jumps when editing starts.
    expect(ta.style.fontSize).toBe("1.25rem");
  });
});
