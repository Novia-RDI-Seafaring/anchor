/**
 * GhostPreview tests (#344) — the read-only diff drawn in place.
 *
 * Pins: selecting a suggestion renders overlay elements for its ops
 * (added dashed, removed dimmed + struck, updated with an old → new label
 * badge, added edges dashed, removed edges dimmed), the overlay clears on
 * deselect, and the component never writes to the workspace store or
 * calls a write API. The API modules are mocked so any call would be
 * visible.
 */
import { ReactFlowProvider } from "@xyflow/react";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import { canvases } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { CANVAS_EDGES, CANVAS_NODES, makeFullThread } from "@/threads/fixtures";
import { useThreadsStore } from "@/threads/threadsStore";

import { GhostPreview } from "./GhostPreview";

vi.mock("@/api/client", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn(), upload: vi.fn() },
  BACKEND_URL: "",
}));
vi.mock("@/api/canvases", () => ({
  canvases: new Proxy(
    {},
    { get: () => vi.fn(() => { throw new Error("ghost preview must not call the canvas API"); }) },
  ),
}));

function mount() {
  return render(
    <ReactFlowProvider>
      <GhostPreview />
    </ReactFlowProvider>,
  );
}

beforeEach(() => {
  useCanvasStore.setState({ nodes: { ...CANVAS_NODES }, edges: { ...CANVAS_EDGES }, version: 20 });
  useThreadsStore.setState({
    openThreadId: "t1",
    thread: makeFullThread(),
    previewItemId: null,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GhostPreview", () => {
  it("renders nothing without a selected suggestion", () => {
    mount();
    expect(screen.queryByTestId("ghost-preview")).toBeNull();
  });

  it("projects the suggestion's ops as overlay elements", () => {
    useThreadsStore.setState({ previewItemId: "s1" });
    mount();
    expect(screen.getByTestId("ghost-preview").getAttribute("data-item-id")).toBe("s1");

    const nodes = screen.getAllByTestId("ghost-node");
    const kinds = nodes.map((n) => n.getAttribute("data-ghost-kind"));
    expect(kinds).toEqual(["node-added", "node-updated", "node-removed"]);

    const added = nodes[0]!;
    expect(added.style.left).toBe("400px");
    expect(added.style.top).toBe("40px");
    expect(added.style.border).toContain("dashed");
    expect(added.textContent).toContain("Cooling loop");

    expect(screen.getByTestId("ghost-diff-badge").textContent).toBe("Pump → Pump P-101");

    const removed = nodes[2]!;
    expect(removed.getAttribute("data-node-id")).toBe("n2");
    expect(removed.querySelector(".line-through")).toBeTruthy();

    const edges = screen.getAllByTestId("ghost-edge");
    expect(edges.map((e) => e.getAttribute("data-ghost-kind"))).toEqual(["edge-added", "edge-removed"]);
    const addedLine = edges[0]!.querySelector("line")!;
    expect(addedLine.getAttribute("stroke-dasharray")).toBe("6 4");
    const removedLine = edges[1]!.querySelector("line")!;
    expect(removedLine.getAttribute("stroke-dasharray")).toBeNull();
    expect(removedLine.getAttribute("opacity")).toBe("0.5");
  });

  it("clears on deselect", () => {
    useThreadsStore.setState({ previewItemId: "s1" });
    mount();
    expect(screen.getByTestId("ghost-preview")).toBeTruthy();
    act(() => {
      useThreadsStore.setState({ previewItemId: null });
    });
    expect(screen.queryByTestId("ghost-preview")).toBeNull();
  });

  it("never mutates the workspace store or calls a write API", () => {
    const before = useCanvasStore.getState();
    const setState = vi.spyOn(useCanvasStore, "setState");
    const applyEvent = vi.spyOn(before, "applyEvent");
    useThreadsStore.setState({ previewItemId: "s1" });
    const { unmount } = mount();
    expect(screen.getAllByTestId("ghost-node")).toHaveLength(3);
    unmount();

    expect(setState).not.toHaveBeenCalled();
    expect(applyEvent).not.toHaveBeenCalled();
    const after = useCanvasStore.getState();
    expect(after.nodes).toBe(before.nodes);
    expect(after.edges).toBe(before.edges);
    expect(after.version).toBe(20);
    for (const fn of [api.post, api.patch, api.del]) expect(fn).not.toHaveBeenCalled();
    // The canvases module proxy throws on any access; touching it here
    // proves the mock is live without the component having done so.
    expect(() => canvases.addNode("plant", {})).toThrow();
  });
});
