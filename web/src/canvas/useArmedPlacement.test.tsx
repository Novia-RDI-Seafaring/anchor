import { useRef } from "react";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";
import { useArmedPlacement } from "./useArmedPlacement";

vi.mock("@/api/canvases", () => ({ canvases: { addNode: vi.fn(), createSubCanvas: vi.fn() } }));
vi.mock("./registry", () => ({ CONNECT_TOOL: "__connect__", INTENT_TOOL: "__intent__", paletteEntries: (group: string) => group === "shapes" ? [
  { name: "concept", meta: { nodeType: "concept", label: "Rectangle", noDefaultLabel: true, width: 160, height: 60, data: { variant: "rectangle" } } },
  { name: "area", meta: { nodeType: "area", label: "Area", width: 360, height: 220 } },
] : [] }));
const adopt = vi.fn<(...args: [string, { x: number; y: number }]) => Promise<void>>();
const subResult: Awaited<ReturnType<typeof canvases.createSubCanvas>> = {
  child: { slug: "a-sub-fixed", title: "Sub-canvas", created_at: 0 },
  node: { id: "placed", node_type: "canvas", label: "Sub-canvas", x: 10, y: 20, data: {} },
  event: { payload: { id: "placed" } },
  state: { slug: "a", title: "Test", version: 1, nodes: [], edges: [], metadata: {} },
};

function Probe({ slug = "a", active = true, size }: { slug?: string; active?: boolean; size?: { width: number; height: number } }) {
  const armedTool = useUiStore((state) => state.armedTool);
  const place = useArmedPlacement({ slug, active, armedTool, makeSubCanvasSlug: () => `${slug}-sub-fixed`, adoptIntoRegion: adopt });
  const down = useRef(false);
  return <div data-testid="pane" onPointerDown={() => { down.current = true; }} onPointerUp={() => {
    if (down.current) { down.current = false; void place(10, 20, size); }
  }} />;
}
function gesture(pane: Element) { fireEvent.pointerDown(pane); fireEvent.pointerUp(pane); }
function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
beforeEach(() => {
  vi.clearAllMocks();
  useCanvasStore.setState({ slug: "a" });
  useUiStore.setState({ armedTool: "concept", navigationMode: "select", selectedNodeId: null, pendingInlineRenameNodeId: null });
  vi.mocked(canvases.addNode).mockResolvedValue({ event: { payload: { id: "placed" } } });
  vi.mocked(canvases.createSubCanvas).mockResolvedValue(subResult);
  adopt.mockResolvedValue();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each(["concept", "canvas"])("submits one %s for two pointer cycles while the first API request is unresolved", async (tool) => {
  useUiStore.setState({ armedTool: tool });
  const save = deferred<typeof subResult>();
  const api = tool === "canvas" ? vi.mocked(canvases.createSubCanvas) : vi.mocked(canvases.addNode);
  api.mockReturnValueOnce(save.promise);
  const view = render(<Probe />);
  gesture(view.getByTestId("pane")); gesture(view.getByTestId("pane"));
  expect(api).toHaveBeenCalledTimes(1);
  await act(async () => save.resolve(subResult));
  expect(useUiStore.getState().armedTool).toBeNull();
  if (tool === "canvas") expect(api).toHaveBeenCalledWith("a", { slug: "a-sub-fixed", title: "Sub-canvas", x: 10, y: 20 });
  else {
    expect(useUiStore.getState().selectedNodeId).toBe("placed");
    expect(useUiStore.getState().pendingInlineRenameNodeId).toBe("placed");
    expect(adopt).toHaveBeenCalledExactlyOnceWith("placed", { x: 90, y: 50 });
  }
});

it("preserves drag size and keeps the guard through pending region adoption", async () => {
  const joining = deferred(); adopt.mockReturnValueOnce(joining.promise.then(() => {}));
  const view = render(<Probe size={{ width: 240, height: 100 }} />);
  gesture(view.getByTestId("pane"));
  await waitFor(() => expect(adopt).toHaveBeenCalledExactlyOnceWith("placed", { x: 130, y: 70 }));
  gesture(view.getByTestId("pane"));
  expect(canvases.addNode).toHaveBeenCalledExactlyOnceWith("a", { node_type: "concept", label: "", x: 10, y: 20, width: 240, height: 100, data: { variant: "rectangle", width: 240, height: 100 } });
  await act(async () => joining.resolve(undefined));
  expect(useUiStore.getState().armedTool).toBeNull();
});

it.each(["concept", "canvas"])("releases failed %s placement and allows an explicitly re-armed gesture", async (tool) => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  useUiStore.setState({ armedTool: tool });
  const save = deferred<typeof subResult>();
  const api = tool === "canvas" ? vi.mocked(canvases.createSubCanvas) : vi.mocked(canvases.addNode);
  api.mockReturnValueOnce(save.promise);
  const view = render(<Probe />); gesture(view.getByTestId("pane")); gesture(view.getByTestId("pane"));
  await act(async () => save.reject(new Error("Offline")));
  expect(useUiStore.getState().armedTool).toBeNull();
  expect(useUiStore.getState().selectedNodeId).toBeNull();
  act(() => useUiStore.getState().armTool(tool));
  gesture(view.getByTestId("pane"));
  await waitFor(() => expect(useUiStore.getState().armedTool).toBeNull());
  expect(api).toHaveBeenCalledTimes(2);
});

it("does not adopt a region into another region", async () => {
  useUiStore.setState({ armedTool: "area" });
  const view = render(<Probe />); gesture(view.getByTestId("pane"));
  await waitFor(() => expect(useUiStore.getState().armedTool).toBeNull());
  expect(adopt).not.toHaveBeenCalled();
});

it.each(["route", "read-only", "unmount"])("keeps a pending completion out of a later %s", async (change) => {
  const save = deferred(); vi.mocked(canvases.addNode).mockReturnValueOnce(save.promise);
  const view = render(<Probe />); gesture(view.getByTestId("pane"));
  if (change === "route") {
    act(() => useCanvasStore.setState({ slug: "b" })); view.rerender(<Probe slug="b" />);
  } else if (change === "read-only") view.rerender(<Probe active={false} />);
  else view.unmount();
  await act(async () => save.resolve({ event: { payload: { id: "old" } } }));
  expect(useUiStore.getState().selectedNodeId).toBeNull();
  expect(useUiStore.getState().pendingInlineRenameNodeId).toBeNull();
  expect(useUiStore.getState().armedTool).toBe("concept");
  expect(adopt).not.toHaveBeenCalled();
});

it("leaves a different tool armed when an earlier request finishes", async () => {
  const save = deferred(); vi.mocked(canvases.addNode).mockReturnValueOnce(save.promise);
  const view = render(<Probe />); gesture(view.getByTestId("pane"));
  act(() => useUiStore.getState().armTool("area"));
  await act(async () => save.resolve({ event: { payload: { id: "placed" } } }));
  expect(useUiStore.getState().armedTool).toBe("area");
  expect(useUiStore.getState().selectedNodeId).toBeNull();
  expect(useUiStore.getState().pendingInlineRenameNodeId).toBeNull();
});

it.each(["inactive", "stale-store", "connector", "intent", "unarmed"])("rejects %s placement", (state) => {
  if (state === "stale-store") useCanvasStore.setState({ slug: "b" });
  if (state === "connector") useUiStore.setState({ armedTool: "__connect__" });
  if (state === "intent") useUiStore.setState({ armedTool: "__intent__" });
  if (state === "unarmed") useUiStore.setState({ armedTool: null });
  const view = render(<Probe active={state !== "inactive"} />); gesture(view.getByTestId("pane"));
  expect(canvases.addNode).not.toHaveBeenCalled(); expect(canvases.createSubCanvas).not.toHaveBeenCalled();
});
