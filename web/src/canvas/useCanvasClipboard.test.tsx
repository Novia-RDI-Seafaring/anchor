import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useCanvasClipboard } from "./useCanvasClipboard";
import type { ClipboardNode } from "./clipboard";

vi.mock("@/api/canvases", () => ({ canvases: { addNode: vi.fn(), addEdge: vi.fn(), removeNode: vi.fn(), removeEdge: vi.fn(), state: vi.fn() } }));
let gestures: ReturnType<typeof useCanvasClipboard>;
let server: Record<string, ClipboardNode>;
const restored = vi.fn(), selected = vi.fn();
function Probe({ slug = "a", active = true }: { slug?: string; active?: boolean }) {
  gestures = useCanvasClipboard({ slug, active,
    nodes: () => Object.values(useCanvasStore.getState().nodes).map((n) => ({ id: n.id, position: { x: n.x, y: n.y }, data: {}, selected: n.id === "a" || n.id === "child" })),
    edges: () => [], toFlow: (p) => ({ x: p.x / 2, y: p.y / 2 }), restore: restored, select: selected });
  return <><input aria-label="text" /><div role="textbox" contentEditable suppressContentEditableWarning>editable</div><output>{gestures.error}</output></>;
}
beforeEach(() => {
  vi.resetAllMocks();
  server = { a: { id: "a", node_type: "area", label: "A", x: 10, y: 20 },
    child: { id: "child", node_type: "spec", label: "Child", x: 30, y: 40, parent: "a" } };
  useCanvasStore.getState().reset();
  useCanvasStore.setState({ slug: "a", nodes: structuredClone(server), edges: {} });
  vi.mocked(canvases.addNode).mockImplementation(async (_slug, body) => {
    const n = body as ClipboardNode;
    if (n.parent && !server[n.parent]) throw new Error("Parent is missing");
    server[n.id] = n; return {};
  });
  vi.mocked(canvases.removeNode).mockImplementation(async (_slug, id) => {
    if (!server[id]) throw new Error("Node is missing");
    delete server[id];
    for (const n of Object.values(server)) if (n.parent === id) delete server[n.id];
    return {};
  });
  vi.mocked(canvases.removeEdge).mockResolvedValue({});
  vi.mocked(canvases.state).mockImplementation(async (slug) => ({ slug, title: "", version: 1, nodes: Object.values(server), edges: [], metadata: {} }));
});
afterEach(cleanup);
const key = (key: string, target: Window | Element = window, modifiers: { ctrlKey?: boolean; metaKey?: boolean } = { ctrlKey: true }) => fireEvent.keyDown(target, { key, ...modifiers });

describe("canvas clipboard gestures", () => {
  it("copies with Cmd+C and pastes with Ctrl+V using fresh IDs and repeated offsets", async () => {
    render(<Probe />);
    key("c", window, { metaKey: true });
    key("v");
    await waitFor(() => expect(selected).toHaveBeenCalledOnce());
    expect(canvases.addNode).toHaveBeenNthCalledWith(1, "a", expect.objectContaining({ x: 34, y: 44, parent: null }));
    const parent = vi.mocked(canvases.addNode).mock.calls[0]![1].id;
    expect(canvases.addNode).toHaveBeenNthCalledWith(2, "a", expect.objectContaining({ x: 54, y: 64, parent }));
    key("v");
    await waitFor(() => expect(selected).toHaveBeenCalledTimes(2));
    expect(canvases.addNode).toHaveBeenNthCalledWith(3, "a", expect.objectContaining({ x: 58, y: 68 }));
    expect(new Set(vi.mocked(canvases.addNode).mock.calls.map((c) => c[1].id)).size).toBe(4);
  });

  it("cuts children before their parents and retains the fragment for paste", async () => {
    render(<Probe />); key("x");
    await waitFor(() => expect(Object.keys(useCanvasStore.getState().nodes)).toHaveLength(0));
    expect(vi.mocked(canvases.removeNode).mock.calls.map((c) => c[1])).toEqual(["child", "a"]);
    key("v");
    await waitFor(() => expect(selected).toHaveBeenCalledOnce());
    expect(Object.keys(server)).toHaveLength(2);
  });

  it("uses the session clipboard on a second canvas", async () => {
    const view = render(<Probe />); key("c");
    server = {}; useCanvasStore.setState({ slug: "b", nodes: {}, edges: {} });
    view.rerender(<Probe slug="b" />); key("v");
    await waitFor(() => expect(selected).toHaveBeenCalledOnce());
    expect(canvases.addNode).toHaveBeenCalledWith("b", expect.objectContaining({ label: "A" }));
  });

  it("leaves native text and contenteditable clipboard events untouched", async () => {
    const view = render(<Probe />); key("c");
    for (const field of [view.getByLabelText("text"), view.getByRole("textbox", { name: "" })]) {
      const event = new KeyboardEvent("keydown", { key: "v", ctrlKey: true, bubbles: true, cancelable: true });
      fireEvent(field, event); expect(event.defaultPrevented).toBe(false);
    }
    await act(async () => {});
    expect(canvases.addNode).not.toHaveBeenCalled();
  });

  it("restores originals and clones a multi-selection exactly once at the world-space drag delta", async () => {
    render(<Probe />);
    act(() => {
      gestures.startDrag({ altKey: true, clientX: 100, clientY: 200 }, ["a", "child"]);
      expect(gestures.finishDrag({ clientX: 180, clientY: 240 })).toBe(true);
      expect(gestures.finishDrag({ clientX: 180, clientY: 240 })).toBe(true);
    });
    await waitFor(() => expect(selected).toHaveBeenCalledOnce());
    expect(restored).toHaveBeenCalledOnce();
    expect(server.a).toMatchObject({ x: 10, y: 20 });
    expect(canvases.addNode).toHaveBeenCalledTimes(2);
    expect(canvases.addNode).toHaveBeenNthCalledWith(1, "a", expect.objectContaining({ x: 50, y: 40 }));
    act(() => gestures.startDrag({ altKey: false, clientX: 0, clientY: 0 }, ["a"]));
    expect(gestures.finishDrag({ clientX: 2, clientY: 2 })).toBe(false);
  });

  it("rolls back a partially created paste and shows its failure", async () => {
    vi.mocked(canvases.addNode).mockImplementationOnce(async (_slug, body) => {
      const n = body as ClipboardNode;
      server[n.id] = n;
      return {};
    }).mockRejectedValueOnce(new Error("Server unavailable"));
    const view = render(<Probe />); key("c"); key("v");
    await waitFor(() => expect(view.getByText(/Paste failed/)).toBeTruthy());
    expect(canvases.removeNode).toHaveBeenCalledTimes(2);
    expect(Object.keys(server).sort()).toEqual(["a", "child"]);
    expect(selected).not.toHaveBeenCalled();
  });

  it("does not handle clipboard keys when inactive", () => {
    render(<Probe active={false} />); key("v");
    expect(canvases.addNode).not.toHaveBeenCalled();
  });
});
