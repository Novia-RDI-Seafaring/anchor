import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";
import { usePaneText } from "./usePaneText";

vi.mock("@/api/canvases", () => ({ canvases: { addNode: vi.fn() } }));
const toFlow = vi.fn(({ x, y }: { x: number; y: number }) => ({ x: (x - 100) / 2, y: (y - 50) / 2 }));

function Probe({ slug = "a", active = true }: { slug?: string; active?: boolean }) {
  const text = usePaneText({ slug, active, toFlow });
  return <div onMouseDownCapture={text.onMouseDownCapture} onDoubleClickCapture={text.onDoubleClickCapture}>
    <div className="react-flow__pane" data-testid="pane"><div className="react-flow__node" data-testid="node">Label</div>
      <button>Control</button><input aria-label="Editor" /></div>
    <div role="dialog"><div className="react-flow__pane" data-testid="dialog">Preview</div></div>
    <div data-canvas-read-only="true"><div className="react-flow__pane" data-testid="monitor">Monitor</div></div>
    {text.error ? <p role="alert">{text.error}</p> : null}
  </div>;
}

function doubleClick(target: Element, options = {}) {
  fireEvent.mouseDown(target, { detail: 1, ...options });
  fireEvent.mouseDown(target, { detail: 2, ...options });
  return fireEvent.doubleClick(target, { detail: 2, clientX: 300, clientY: 250, ...options });
}

beforeEach(() => {
  vi.clearAllMocks();
  useCanvasStore.setState({ slug: "a" });
  useUiStore.setState({ selectedNodeId: null, pendingInlineRenameNodeId: null });
  vi.mocked(canvases.addNode).mockResolvedValue({ event: { payload: { id: "text-1" } } });
});
afterEach(cleanup);

it("persists one existing text node at transformed coordinates and requests its editor", async () => {
  const view = render(<Probe />);
  expect(doubleClick(view.getByTestId("pane"))).toBe(false);
  await waitFor(() => expect(useUiStore.getState().pendingInlineRenameNodeId).toBe("text-1"));
  expect(canvases.addNode).toHaveBeenCalledExactlyOnceWith("a", { node_type: "text", label: "", x: 100, y: 100, data: { text: "" } });
  expect(useUiStore.getState().selectedNodeId).toBe("text-1");
});

it("leaves nodes, controls, editors, dialog previews and monitor panes untouched", () => {
  const view = render(<Probe />);
  for (const target of [view.getByTestId("node"), view.getByRole("button"), view.getByLabelText("Editor"), view.getByTestId("dialog"), view.getByTestId("monitor")]) {
    expect(doubleClick(target)).toBe(true);
  }
  expect(canvases.addNode).not.toHaveBeenCalled();
});

it("does not turn the first click of an armed tool, Hand, markup or read-only mode into text", () => {
  const view = render(<Probe active={false} />);
  fireEvent.mouseDown(view.getByTestId("pane"), { detail: 1 });
  view.rerender(<Probe active />);
  fireEvent.mouseDown(view.getByTestId("pane"), { detail: 2 });
  fireEvent.doubleClick(view.getByTestId("pane"), { detail: 2 });
  expect(canvases.addNode).not.toHaveBeenCalled();
  view.rerender(<Probe active={false} />);
  expect(doubleClick(view.getByTestId("pane"))).toBe(true);
  expect(canvases.addNode).not.toHaveBeenCalled();
});

it("keeps modified and non-primary double-clicks native", () => {
  const view = render(<Probe />);
  for (const options of [{ ctrlKey: true }, { shiftKey: true }, { altKey: true }, { metaKey: true }, { button: 1 }]) doubleClick(view.getByTestId("pane"), options);
  expect(canvases.addNode).not.toHaveBeenCalled();
});

it("does not create text when the route changes between clicks", () => {
  const view = render(<Probe />);
  fireEvent.mouseDown(view.getByTestId("pane"), { detail: 1 });
  view.rerender(<Probe slug="b" />);
  fireEvent.mouseDown(view.getByTestId("pane"), { detail: 2 });
  fireEvent.doubleClick(view.getByTestId("pane"), { detail: 2 });
  expect(canvases.addNode).not.toHaveBeenCalled();
});

it.each(["route", "mode"])("cannot focus a new %s when an earlier creation completes", async (change) => {
  let resolve!: (value: unknown) => void;
  vi.mocked(canvases.addNode).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  const view = render(<Probe />);
  doubleClick(view.getByTestId("pane"));
  if (change === "route") {
    act(() => useCanvasStore.setState({ slug: "b" }));
    view.rerender(<Probe slug="b" />);
  } else view.rerender(<Probe active={false} />);
  await act(async () => resolve({ event: { payload: { id: "old-text" } } }));
  expect(useUiStore.getState().pendingInlineRenameNodeId).toBeNull();
  expect(useUiStore.getState().selectedNodeId).toBeNull();
});

it("reports a failed save without stealing selection", async () => {
  vi.mocked(canvases.addNode).mockRejectedValueOnce(new Error("Offline"));
  const view = render(<Probe />); doubleClick(view.getByTestId("pane"));
  await waitFor(() => expect(view.getByRole("alert").textContent).toContain("Could not create text: Offline"));
  expect(useUiStore.getState().selectedNodeId).toBeNull();
});
