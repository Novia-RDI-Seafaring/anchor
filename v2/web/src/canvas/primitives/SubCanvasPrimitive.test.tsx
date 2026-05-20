/**
 * SubCanvasPrimitive smoke test — pin the rendered title, the snapshot
 * placeholder, and the breadcrumb cycle-prevention badge.
 *
 * Navigation itself is wired in CanvasGraph.onNodeDoubleClick (see
 * `breadcrumb.enter(target); navigate(/c/<target>)`); this test asserts
 * the primitive contributes the necessary surface — the title shows, the
 * breadcrumb-aware badge appears when the slug is in the chain.
 */
import { act, render, screen } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { breadcrumb } from "@/canvas/breadcrumb";
import { SubCanvasPrimitive } from "./SubCanvasPrimitive";

// Stub the snapshot fetch so jsdom doesn't actually hit the network. The
// thumbnail load fires on mount; without a stub the component's
// setThumbState calls would yell into the console without affecting the
// assertions, but the stub also keeps the act warnings tidy.
beforeEach(() => {
  breadcrumb.clear();
  // Also stub URL.createObjectURL — jsdom doesn't implement it.
  if (!URL.createObjectURL) {
    (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = () =>
      "blob:stub";
  }
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(new Blob([new Uint8Array([0])]), {
      status: 200,
      headers: { "content-type": "image/png" },
    })),
  );
});

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
    await renderTile({ data: { canvas_slug: "child", title: "Pump Loop" } });
    expect(screen.getByText("Pump Loop")).toBeTruthy();
    expect(screen.getByText("canvas")).toBeTruthy();
  });

  it("falls back to the canvas_slug when no title is set", async () => {
    await renderTile({ data: { canvas_slug: "heat-ex" } });
    expect(screen.getByText("heat-ex")).toBeTruthy();
  });

  it("does NOT show the already-visiting badge for a fresh chain", async () => {
    await renderTile({ data: { canvas_slug: "fresh-child" } });
    expect(screen.queryByText(/already visiting/)).toBeNull();
  });

  it("shows the already-visiting badge when the slug is in the breadcrumb chain", async () => {
    breadcrumb.reset("parent");
    breadcrumb.enter("looped");
    await renderTile({ data: { canvas_slug: "looped" } });
    expect(screen.getByText(/already visiting/)).toBeTruthy();
  });
});
