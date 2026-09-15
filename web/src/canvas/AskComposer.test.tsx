/**
 * AskComposer tests (#344) — the scoped ask.
 *
 * Pins: the composer renders for the selection the threads store names,
 * its chips follow the selected node types, Enter / a chip click posts
 * the ask with the selection as `nodeIds` (→ `targets[]`), and a
 * successful ask opens the new thread and closes the composer.
 */
import { ReactFlowProvider } from "@xyflow/react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as intentsApi from "@/api/intents";
import { useCanvasStore } from "@/stores/canvasStore";
import { CANVAS_NODES, makeThread } from "@/threads/fixtures";
import { useThreadsStore } from "@/threads/threadsStore";

import { AskComposer } from "./AskComposer";

function mount() {
  return render(
    <ReactFlowProvider>
      <AskComposer workspaceSlug="plant" />
    </ReactFlowProvider>,
  );
}

beforeEach(() => {
  useCanvasStore.setState({ nodes: { ...CANVAS_NODES } });
  useThreadsStore.setState({ composerNodeIds: null, openThreadId: null, thread: null });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AskComposer", () => {
  it("renders nothing until a selection is armed", () => {
    mount();
    expect(screen.queryByTestId("ask-composer")).toBeNull();
  });

  it("anchors under the selection and derives chips from the node types", () => {
    useThreadsStore.setState({ composerNodeIds: ["n1", "n2"] });
    mount();
    const el = screen.getByTestId("ask-composer");
    // Without a mounted pane flow == screen: bbox of n1+n2 is x10..280, y20..160.
    expect(el.style.left).toBe("10px");
    expect(el.style.top).toBe(`${160 + 12}px`);
    expect(screen.getAllByTestId("ask-composer-chip").map((c) => c.textContent)).toEqual([
      "Fill the missing values from the documents",
      "Verify these against the source",
      "Extract the specs into a table",
      "Compare these",
      "Check consistency",
      "Make sense of this",
      "Name and group these",
    ]);
  });

  it("Enter posts the ask with the selection and opens the new thread", async () => {
    const ask = vi
      .spyOn(intentsApi.intents, "ask")
      .mockResolvedValue(makeThread({ id: "t-new" }));
    useThreadsStore.setState({ composerNodeIds: ["n1", "n2"] });
    mount();

    fireEvent.change(screen.getByTestId("ask-composer-input"), {
      target: { value: "  what is this?  " },
    });
    await act(async () => {
      fireEvent.keyDown(screen.getByTestId("ask-composer-input"), { key: "Enter" });
    });

    expect(ask).toHaveBeenCalledWith({
      text: "what is this?",
      workspaceSlug: "plant",
      nodeIds: ["n1", "n2"],
    });
    expect(useThreadsStore.getState().openThreadId).toBe("t-new");
    expect(useThreadsStore.getState().composerNodeIds).toBeNull();
    expect(screen.queryByTestId("ask-composer")).toBeNull();
  });

  it("a chip click submits the chip text", async () => {
    const ask = vi.spyOn(intentsApi.intents, "ask").mockResolvedValue(makeThread());
    useThreadsStore.setState({ composerNodeIds: ["n3"] });
    mount();
    await act(async () => {
      fireEvent.click(screen.getByText("Digitize this curve"));
    });
    expect(ask).toHaveBeenCalledWith({
      text: "Digitize this curve",
      workspaceSlug: "plant",
      nodeIds: ["n3"],
    });
  });

  it("Shift+Enter keeps typing; an empty draft never posts", async () => {
    const ask = vi.spyOn(intentsApi.intents, "ask").mockResolvedValue(makeThread());
    useThreadsStore.setState({ composerNodeIds: ["n1"] });
    mount();
    await act(async () => {
      fireEvent.keyDown(screen.getByTestId("ask-composer-input"), { key: "Enter" });
      fireEvent.keyDown(screen.getByTestId("ask-composer-input"), { key: "Enter", shiftKey: true });
    });
    expect(ask).not.toHaveBeenCalled();
    expect((screen.getByTestId("ask-composer-submit") as HTMLButtonElement).disabled).toBe(true);
  });

  it("surfaces a failed ask inline and stays open", async () => {
    vi.spyOn(intentsApi.intents, "ask").mockRejectedValue(new Error("nope"));
    useThreadsStore.setState({ composerNodeIds: ["n1"] });
    mount();
    fireEvent.change(screen.getByTestId("ask-composer-input"), { target: { value: "x" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("ask-composer-submit"));
    });
    expect(screen.getByTestId("ask-composer-error").textContent).toContain("nope");
    expect(useThreadsStore.getState().composerNodeIds).toEqual(["n1"]);
  });

  it("Escape and the close button dismiss it", () => {
    useThreadsStore.setState({ composerNodeIds: ["n1"] });
    mount();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(useThreadsStore.getState().composerNodeIds).toBeNull();
    act(() => {
      useThreadsStore.setState({ composerNodeIds: ["n1"] });
    });
    fireEvent.click(screen.getByTestId("ask-composer-close"));
    expect(useThreadsStore.getState().composerNodeIds).toBeNull();
  });
});
