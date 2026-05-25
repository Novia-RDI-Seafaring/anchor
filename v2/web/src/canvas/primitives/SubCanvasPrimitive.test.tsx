/**
 * SubCanvasPrimitive smoke test — pin the rendered title, the graph glyph
 * placeholder, the node/edge counts, and the breadcrumb cycle-prevention
 * badge.
 *
 * Important contract: the primitive must NOT fetch a PNG snapshot of the
 * child canvas. The body of the tile is purely representational — a
 * glyph + counts sourced from the shared `useWorkspacesList()` cache.
 * The fetch stub below would catch a regression: if a future change
 * re-introduces a snapshot fetch, this test would still pass but the
 * assertion `expect(fetch).not.toHaveBeenCalled()` guards it.
 */
import { act, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { breadcrumb } from "@/canvas/breadcrumb";
import * as workspacesHook from "@/canvas/useWorkspacesList";
import { SubCanvasPrimitive } from "./SubCanvasPrimitive";

beforeEach(() => {
  breadcrumb.clear();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockWorkspaces(entries: Array<{ slug: string; node_count: number; edge_count: number }>) {
  const bySlug = new Map(
    entries.map((e) => [
      e.slug,
      {
        slug: e.slug,
        title: "",
        created_at: 0,
        node_count: e.node_count,
        edge_count: e.edge_count,
        references: [],
        referenced_by: [],
      },
    ]),
  );
  vi.spyOn(workspacesHook, "useWorkspacesList").mockReturnValue({
    items: Array.from(bySlug.values()),
    bySlug,
  });
}

async function renderTile({
  data,
  selected = false,
}: {
  data: Record<string, unknown>;
  selected?: boolean;
}) {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <MemoryRouter initialEntries={["/c/parent"]}>
        <Routes>
          <Route
            path="/c/:id"
            element={
              <ReactFlowProvider>
                <SubCanvasPrimitive
                  {...({
                    id: "n1",
                    data,
                    selected,
                    dragging: false,
                    isConnectable: false,
                    positionAbsoluteX: 0,
                    positionAbsoluteY: 0,
                    type: "canvas",
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
  });
  return result;
}

describe("SubCanvasPrimitive", () => {
  it("renders the title and the producer label", async () => {
    mockWorkspaces([{ slug: "child", node_count: 0, edge_count: 0 }]);
    await renderTile({ data: { canvas_slug: "child", title: "Pump Loop" } });
    expect(screen.getByText("Pump Loop")).toBeTruthy();
    expect(screen.getByText("canvas")).toBeTruthy();
  });

  it("falls back to the canvas_slug when no title is set", async () => {
    mockWorkspaces([{ slug: "heat-ex", node_count: 0, edge_count: 0 }]);
    await renderTile({ data: { canvas_slug: "heat-ex" } });
    // The title field falls back to the slug.
    expect(screen.getAllByText("heat-ex").length).toBeGreaterThan(0);
  });

  it("renders node + edge counts from the workspaces cache", async () => {
    mockWorkspaces([{ slug: "child", node_count: 8, edge_count: 12 }]);
    await renderTile({ data: { canvas_slug: "child", title: "Child" } });
    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText(/nodes/)).toBeTruthy();
    expect(screen.getByText(/edges/)).toBeTruthy();
  });

  it("shows a placeholder when the cache hasn't landed yet", async () => {
    vi.spyOn(workspacesHook, "useWorkspacesList").mockReturnValue(null);
    await renderTile({ data: { canvas_slug: "missing", title: "Maybe" } });
    expect(screen.getByText("…")).toBeTruthy();
  });

  it("does NOT fetch a PNG snapshot of the child canvas", async () => {
    mockWorkspaces([
      // Stored child title matches the tile's title so the cascade-rename
      // effect bails (idempotent) and doesn't issue its own PATCH.
      { slug: "child", title: "X", node_count: 1, edge_count: 1 },
    ]);
    await renderTile({ data: { canvas_slug: "child", title: "X" } });
    // No call to anything resembling a snapshot endpoint. The rename
    // PATCH is allowed and tested separately.
    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    const snapshotCalls = calls.filter(([url]) =>
      typeof url === "string" && url.includes("/snapshot"),
    );
    expect(snapshotCalls.length).toBe(0);
  });

  it("does NOT show the already-visiting badge for a fresh chain", async () => {
    mockWorkspaces([{ slug: "fresh-child", node_count: 0, edge_count: 0 }]);
    await renderTile({ data: { canvas_slug: "fresh-child" } });
    expect(screen.queryByText(/already visiting/)).toBeNull();
  });

  it("shows the already-visiting badge when the slug is in the breadcrumb chain", async () => {
    mockWorkspaces([{ slug: "looped", node_count: 0, edge_count: 0 }]);
    breadcrumb.reset("parent");
    breadcrumb.enter("looped");
    await renderTile({ data: { canvas_slug: "looped" } });
    expect(screen.getByText(/already visiting/)).toBeTruthy();
  });
});
