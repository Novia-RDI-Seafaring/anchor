/**
 * CanvasesPanel smoke tests — pin the filter (self-link + already-linked
 * exclusion) and the drag payload contract.
 *
 * The drop side of the contract is owned by CanvasGraph; here we verify
 * only that the row sets `application/x-anchor-canvas-link` with the
 * expected JSON keys. The canvas's drop handler is tested elsewhere.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as canvasesApi from "@/api/canvases";
import type { WorkspaceListEntry } from "@/api/canvases";

import {
  CANVAS_LINK_MIME,
  CanvasesPanel,
  filterAttachable,
} from "./CanvasesPanel";

function entry(
  slug: string,
  references: string[] = [],
  extra: Partial<WorkspaceListEntry> = {},
): WorkspaceListEntry {
  return {
    slug,
    title: extra.title ?? "",
    created_at: 0,
    node_count: extra.node_count ?? 0,
    edge_count: extra.edge_count ?? 0,
    references,
    referenced_by: extra.referenced_by ?? [],
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("filterAttachable", () => {
  it("excludes the current canvas", () => {
    const items = [entry("a"), entry("b"), entry("c")];
    const out = filterAttachable(items, "b");
    expect(out.map((e) => e.slug).sort()).toEqual(["a", "c"]);
  });

  it("excludes canvases already in the current's outgoing references", () => {
    // Current = "a", linked to "b". Only "c" should remain attachable.
    const items = [entry("a", ["b"]), entry("b"), entry("c")];
    const out = filterAttachable(items, "a");
    expect(out.map((e) => e.slug)).toEqual(["c"]);
  });

  it("does not filter when current has no references", () => {
    const items = [entry("a"), entry("b"), entry("c")];
    const out = filterAttachable(items, "a");
    expect(out.map((e) => e.slug).sort()).toEqual(["b", "c"]);
  });

  it("handles a missing current entry gracefully", () => {
    // If `canvases.list()` doesn't include the current slug, we still
    // drop the current canvas from the list and leave the rest alone.
    const items = [entry("a"), entry("b")];
    const out = filterAttachable(items, "missing");
    expect(out.map((e) => e.slug).sort()).toEqual(["a", "b"]);
  });
});

describe("CanvasesPanel", () => {
  it("renders only attachable canvases and emits the link mime on drag-start", async () => {
    const items = [
      entry("home", ["alpha"], { title: "Home" }),
      entry("alpha", [], { title: "Alpha", node_count: 3, edge_count: 2 }),
      entry("beta", [], { title: "Beta", node_count: 5, edge_count: 4 }),
    ];
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue(items);

    render(<CanvasesPanel workspaceSlug="home" />);

    // alpha is already linked from home → must not render. beta is free.
    await waitFor(() => {
      expect(screen.getByText("Beta")).toBeTruthy();
    });
    expect(screen.queryByText("Alpha")).toBeNull();
    expect(screen.queryByText("Home")).toBeNull();

    // Stats line uses envelope counts.
    expect(screen.getByText(/5 nodes · 4 edges/)).toBeTruthy();

    // Drag-start payload assertion.
    const row = screen.getByText("Beta").closest('[draggable="true"]');
    expect(row).toBeTruthy();

    const setData = vi.fn();
    const dataTransfer = {
      setData,
      effectAllowed: "",
    } as unknown as DataTransfer;

    act(() => {
      row?.dispatchEvent(
        Object.assign(new Event("dragstart", { bubbles: true }), {
          dataTransfer,
        }),
      );
    });

    expect(setData).toHaveBeenCalledTimes(1);
    const [mime, raw] = setData.mock.calls[0]!;
    expect(mime).toBe(CANVAS_LINK_MIME);
    const payload = JSON.parse(raw as string);
    expect(payload).toEqual({ slug: "beta", title: "Beta" });
  });

  it("falls back to slug as title when title is empty", async () => {
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([
      entry("home"),
      entry("only-slug", []),
    ]);

    render(<CanvasesPanel workspaceSlug="home" />);

    await waitFor(() => {
      expect(screen.getByText("only-slug")).toBeTruthy();
    });

    const row = screen.getByText("only-slug").closest('[draggable="true"]');
    const setData = vi.fn();
    const dataTransfer = { setData, effectAllowed: "" } as unknown as DataTransfer;

    act(() => {
      row?.dispatchEvent(
        Object.assign(new Event("dragstart", { bubbles: true }), { dataTransfer }),
      );
    });
    const payload = JSON.parse(setData.mock.calls[0]![1] as string);
    expect(payload.slug).toBe("only-slug");
    expect(payload.title).toBe("only-slug");
  });

  it("shows an empty state when no other canvases exist", async () => {
    vi.spyOn(canvasesApi.canvases, "list").mockResolvedValue([entry("home")]);

    render(<CanvasesPanel workspaceSlug="home" />);

    await waitFor(() => {
      expect(screen.getByText(/no other canvases to link/)).toBeTruthy();
    });
  });
});
