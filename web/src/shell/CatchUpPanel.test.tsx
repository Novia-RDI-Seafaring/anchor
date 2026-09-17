/**
 * CatchUpPanel tests (#325) — the "While you were away" summary.
 *
 * Pins the panel contract: it appears only when the canvas version moved
 * past the stored last-seen (fetching the grouped fold), renders actor
 * groups (null actor as "earlier"), stays hidden on a first visit while
 * recording the version, and dismissing hides it with last-seen updated.
 */
import { ReactFlowProvider } from "@xyflow/react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as canvasesApi from "@/api/canvases";
import type { CanvasChanges } from "@/api/canvases";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { lastSeenKey, readLastSeen, writeLastSeen } from "./catchUp";
import { actorName, CatchUpPanel } from "./CatchUpPanel";
import { installFakeStorage, installThrowingStorage } from "./testStorage";

function makeChanges(over: Partial<CanvasChanges> = {}): CanvasChanges {
  return {
    from_version: 2,
    to_version: 5,
    groups: [
      {
        actor: { kind: "agent", label: "claude-code" },
        nodes_added: [{ id: "n1", label: "Pump curve", node_type: "spec" }],
        nodes_updated: [],
        nodes_removed: [{ id: "gone", label: "Old note", node_type: "fact" }],
        edges_added: [],
        edges_updated: [],
        edges_removed: [],
      },
      {
        actor: null,
        nodes_added: [],
        nodes_updated: [{ id: "n2", label: "Inlet", node_type: "concept" }],
        nodes_removed: [],
        edges_added: [],
        edges_updated: [],
        edges_removed: [],
      },
    ],
    ...over,
  };
}

function setCanvas(version: number) {
  useCanvasStore.setState({
    slug: "plant",
    version,
    nodes: {
      n1: { id: "n1", node_type: "spec", label: "Pump curve", x: 10, y: 20, width: 100, height: 50 },
      n2: { id: "n2", node_type: "concept", label: "Inlet", x: 0, y: 0 },
    },
  });
}

function renderPanel() {
  return render(
    <ReactFlowProvider>
      <CatchUpPanel workspaceSlug="plant" />
    </ReactFlowProvider>,
  );
}

let restore: () => void;
let storage: ReturnType<typeof installFakeStorage>["storage"];

beforeEach(() => {
  ({ storage, restore } = installFakeStorage());
  useUiStore.setState({ selectedNodeId: null });
  useCanvasStore.setState({ slug: null, version: 0, nodes: {} });
});

afterEach(() => {
  restore();
  vi.restoreAllMocks();
});

it("shows the grouped summary when the canvas is ahead of last-seen", async () => {
  writeLastSeen("plant", 2);
  const changes = vi
    .spyOn(canvasesApi.canvases, "changes")
    .mockResolvedValue(makeChanges());
  setCanvas(5);
  renderPanel();

  expect(await screen.findByTestId("catch-up-panel")).toBeTruthy();
  expect(changes).toHaveBeenCalledWith("plant", 2);
  // Actor label + the "earlier" bucket for pre-attribution events.
  const groups = screen.getAllByTestId("catch-up-group");
  expect(groups[0]!.textContent).toContain("claude-code");
  expect(groups[1]!.textContent).toContain("earlier");
  expect(screen.getByText("Pump curve")).toBeTruthy();
  // Rendering the panel records the new version as seen.
  expect(readLastSeen("plant")).toBe(5);
});

it("stays hidden on a first visit and records the version", () => {
  const changes = vi.spyOn(canvasesApi.canvases, "changes");
  setCanvas(5);
  renderPanel();

  expect(screen.queryByTestId("catch-up-panel")).toBeNull();
  expect(changes).not.toHaveBeenCalled();
  expect(readLastSeen("plant")).toBe(5);
});

it("stays hidden when caught up", () => {
  writeLastSeen("plant", 5);
  const changes = vi.spyOn(canvasesApi.canvases, "changes");
  setCanvas(5);
  renderPanel();

  expect(screen.queryByTestId("catch-up-panel")).toBeNull();
  expect(changes).not.toHaveBeenCalled();
});

it("dismiss hides the panel and updates last-seen to the current version", async () => {
  writeLastSeen("plant", 2);
  vi.spyOn(canvasesApi.canvases, "changes").mockResolvedValue(makeChanges());
  setCanvas(5);
  renderPanel();
  await screen.findByTestId("catch-up-panel");

  // A live edit lands while the panel is open.
  act(() => {
    useCanvasStore.setState({ version: 6 });
  });
  fireEvent.click(screen.getByTestId("catch-up-dismiss"));

  expect(screen.queryByTestId("catch-up-panel")).toBeNull();
  expect(readLastSeen("plant")).toBe(6);
});

it("clicking a surviving node's row selects it; removed rows are inert", async () => {
  writeLastSeen("plant", 2);
  vi.spyOn(canvasesApi.canvases, "changes").mockResolvedValue(makeChanges());
  setCanvas(5);
  renderPanel();
  await screen.findByTestId("catch-up-panel");

  const rows = screen.getAllByTestId("catch-up-node-row");
  const alive = rows.find((r) => r.getAttribute("data-node-id") === "n1")!;
  const removed = rows.find((r) => r.getAttribute("data-node-id") === "gone")!;
  expect((removed as HTMLButtonElement).disabled).toBe(true);

  fireEvent.click(alive);
  expect(useUiStore.getState().selectedNodeId).toBe("n1");
});

it("is safe when localStorage throws — no panel, no crash", () => {
  restore();
  ({ restore } = installThrowingStorage());
  const changes = vi.spyOn(canvasesApi.canvases, "changes");
  setCanvas(5);
  expect(() => renderPanel()).not.toThrow();
  expect(screen.queryByTestId("catch-up-panel")).toBeNull();
  expect(changes).not.toHaveBeenCalled();
});

it("actorName renders labels, kinds, and the earlier bucket", () => {
  expect(actorName({ kind: "agent", label: "claude-code" })).toBe("claude-code");
  expect(actorName({ kind: "human" })).toBe("human");
  expect(actorName(null)).toBe("earlier");
});

// Ensure the storage key stays namespaced per canvas (a regression here
// would leak one canvas's last-seen into another).
it("stores last-seen under a per-slug key", () => {
  writeLastSeen("plant", 4);
  expect(storage.getItem(lastSeenKey("plant"))).toBe("4");
  expect(storage.getItem(lastSeenKey("pump"))).toBeNull();
});
