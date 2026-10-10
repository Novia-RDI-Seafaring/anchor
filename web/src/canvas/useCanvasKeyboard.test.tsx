import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";
import type { ClipboardNode } from "./clipboard";
import { useCanvasKeyboard } from "./useCanvasKeyboard";

vi.mock("@/api/canvases", () => ({ canvases: { patchNode: vi.fn(), state: vi.fn() } }));
const duplicate = vi.fn();
let server: Record<string, ClipboardNode>;
let version: number;
function Probe({ active = true, slug = "a", ids = ["parent", "child"], edgeIds = [] }: { active?: boolean; slug?: string; ids?: string[]; edgeIds?: string[] }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const keyboard = useCanvasKeyboard({ rootRef, slug, active, selectedIds: () => ids, selectedEdgeIds: () => edgeIds, duplicate });
  return <><div ref={rootRef}><div className="react-flow">
    <div className="react-flow__node" data-id="parent" tabIndex={0} data-testid="parent"><button>Details</button></div>
    <div className="react-flow__node" data-id="child" tabIndex={0} data-testid="child" />
    <input aria-label="Label" /><select aria-label="Display"><option>Compact</option></select>
  </div><output>{keyboard.error}</output></div><div tabIndex={0} data-testid="pdf">PDF viewer</div></>;
}
beforeEach(() => {
  vi.resetAllMocks(); version = 0;
  server = { parent: { id: "parent", node_type: "area", label: "Group", x: 100, y: 200 },
    child: { id: "child", node_type: "fact", label: "Fact", x: 120, y: 240, parent: "parent", data: { source_ref: { slug: "pdf", page: 1 } } } };
  useCanvasStore.getState().reset();
  useCanvasStore.setState({ slug: "a", nodes: structuredClone(server), edges: {} });
  useUiStore.setState({ pendingInlineRenameNodeId: null });
  vi.mocked(canvases.patchNode).mockImplementation(async (_slug, id, data) => { server[id] = { ...server[id]!, ...data }; version++; return {}; });
  vi.mocked(canvases.state).mockImplementation(async (slug) => ({ slug, title: "", version, nodes: Object.values(server), edges: [], metadata: {} }));
});
afterEach(cleanup);
function key(target: Element, name: string, modifiers = {}) {
  const event = new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true, ...modifiers });
  fireEvent(target, event); return event;
}
describe("saved canvas shortcuts", () => {
  it("starts existing inline rename and routes Ctrl/Cmd-D to safe duplication", () => {
    const view = render(<Probe />);
    expect(key(view.getByTestId("child"), "Enter").defaultPrevented).toBe(true);
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBe("child");
    key(view.getByTestId("child"), "d", { ctrlKey: true });
    key(view.getByTestId("child"), "d", { metaKey: true });
    expect(duplicate).toHaveBeenCalledTimes(2);
  });
  it("persists parent-plus-child nudges exactly once and reloads canonical saved state", async () => {
    const view = render(<Probe />);
    expect(key(view.getByTestId("child"), "ArrowRight").defaultPrevented).toBe(true);
    await waitFor(() => expect(canvases.state).toHaveBeenCalledOnce());
    expect(canvases.patchNode).toHaveBeenNthCalledWith(1, "a", "parent", { x: 105, y: 200 });
    expect(canvases.patchNode).toHaveBeenNthCalledWith(2, "a", "child", { x: 125, y: 240 });
    expect(useCanvasStore.getState().nodes.child).toMatchObject({ x: 125, y: 240, parent: "parent", data: server.child!.data });
    act(() => useCanvasStore.getState().setSnapshot({ slug: "a", title: "", version, nodes: Object.values(server), edges: [], metadata: {} }));
    expect(useCanvasStore.getState().nodes.parent!.x).toBe(105);
  });
  it("serializes repeated keys against saved coordinates even without an SSE echo", async () => {
    const view = render(<Probe ids={["child"]} />);
    key(view.getByTestId("child"), "ArrowRight");
    key(view.getByTestId("child"), "ArrowRight");
    key(view.getByTestId("child"), "ArrowDown", { shiftKey: true });
    await waitFor(() => expect(canvases.state).toHaveBeenCalledTimes(3));
    expect(server.child).toMatchObject({ x: 130, y: 260 });
    expect(useCanvasStore.getState().nodes.child).toMatchObject({ x: 130, y: 260 });
  });
  it("keeps typing, focused controls, viewer arrows and inactive monitor keys native", () => {
    const view = render(<Probe />);
    expect(key(view.getByLabelText("Label"), "Enter").defaultPrevented).toBe(false);
    expect(key(view.getByLabelText("Display"), "d", { ctrlKey: true }).defaultPrevented).toBe(false);
    expect(key(view.getByRole("button", { name: "Details" }), "Enter").defaultPrevented).toBe(false);
    expect(key(view.getByTestId("pdf"), "ArrowRight").defaultPrevented).toBe(false);
    view.rerender(<Probe active={false} />);
    expect(key(view.getByTestId("child"), "ArrowRight").defaultPrevented).toBe(false);
    expect(key(view.getByTestId("child"), "Enter").defaultPrevented).toBe(false);
    expect(duplicate).not.toHaveBeenCalled(); expect(canvases.patchNode).not.toHaveBeenCalled();
  });
  it("leaves an unselected focused node's selection keys intact", () => {
    const view = render(<Probe ids={[]} />);
    expect(key(view.getByTestId("child"), "Enter").defaultPrevented).toBe(false);
    expect(key(view.getByTestId("child"), "d", { ctrlKey: true }).defaultPrevented).toBe(false);
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBeNull();
  });
  it("blocks native unsaved arrow movement from a focused unselected wrapper", () => {
    const view = render(<Probe ids={["parent"]} />);
    expect(key(view.getByTestId("child"), "ArrowRight").defaultPrevented).toBe(true);
    expect(canvases.patchNode).not.toHaveBeenCalled();
    expect(useCanvasStore.getState().nodes.parent!.x).toBe(100);
    view.rerender(<Probe ids={[]} />);
    expect(key(view.getByTestId("child"), "ArrowRight").defaultPrevented).toBe(true);
    expect(canvases.patchNode).not.toHaveBeenCalled();
  });
  it("routes a selected connector alone through the existing safe duplicate path", () => {
    const view = render(<Probe ids={[]} edgeIds={["join"]} />);
    expect(key(view.getByTestId("child"), "d", { ctrlKey: true }).defaultPrevented).toBe(true);
    expect(duplicate).toHaveBeenCalledOnce();
  });
  it("leaves Enter intact for document/model cards with no inline rename editor", () => {
    useCanvasStore.setState({ nodes: { ...useCanvasStore.getState().nodes, child: { ...server.child!, node_type: "document" } } });
    const view = render(<Probe />);
    expect(key(view.getByTestId("child"), "Enter").defaultPrevented).toBe(false);
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBeNull();
  });
  it("shows movement failure and reloads the saved positions", async () => {
    vi.mocked(canvases.patchNode).mockRejectedValueOnce(new Error("Server unavailable"));
    const view = render(<Probe />); key(view.getByTestId("child"), "ArrowLeft");
    await waitFor(() => expect(view.getByText(/Could not move selection: Server unavailable/)).toBeTruthy());
    expect(canvases.state).toHaveBeenCalledOnce();
    expect(useCanvasStore.getState().nodes.child!.x).toBe(120);
  });
  it("does not let a pending old-canvas response replace the new canvas", async () => {
    let release!: () => void;
    vi.mocked(canvases.patchNode).mockImplementationOnce(async () => { await new Promise<void>((resolve) => { release = resolve; }); return {}; });
    const view = render(<Probe ids={["child"]} />); key(view.getByTestId("child"), "ArrowRight");
    act(() => useCanvasStore.setState({ slug: "b", nodes: {}, edges: {} }));
    view.rerender(<Probe slug="b" />);
    await act(async () => release());
    expect(useCanvasStore.getState().slug).toBe("b");
    expect(useCanvasStore.getState().nodes).toEqual({});
  });
});
