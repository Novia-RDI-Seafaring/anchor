/**
 * CanvasTree smoke tests — pin the tree-building math + toggle behaviour.
 *
 * The tree is derived from the `WorkspaceListEntry[]` envelope. We cover:
 *   - Pure root detection (no parent → root).
 *   - Children nested under a parent only after expand.
 *   - DAG: a canvas with two parents renders twice + carries the `↔` badge.
 *   - Cycles: A → B → A renders the cycle as a single tree with the `↩
 *     cycle` chip and stops recursing.
 */
import { render, screen, within, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { WorkspaceListEntry } from "@/api/canvases";

import { CanvasTree, pickRoots } from "./CanvasTree";

function entry(
  slug: string,
  references: string[] = [],
  referenced_by: string[] = [],
  extra: Partial<WorkspaceListEntry> = {},
): WorkspaceListEntry {
  return {
    slug,
    title: extra.title ?? "",
    created_at: 0,
    node_count: extra.node_count ?? 0,
    edge_count: extra.edge_count ?? 0,
    references,
    referenced_by,
  };
}

function renderTree(items: WorkspaceListEntry[]) {
  return render(
    <MemoryRouter>
      <CanvasTree items={items} />
    </MemoryRouter>,
  );
}

describe("pickRoots", () => {
  it("returns canvases with no parent", () => {
    const items = [
      entry("a", ["b"], []),
      entry("b", [], ["a"]),
      entry("c", [], []),
    ];
    expect(pickRoots(items).sort()).toEqual(["a", "c"]);
  });

  it("adopts a cycle's smallest slug as a root when no external parent exists", () => {
    // A ↔ B isolated cycle: each is in the other's referenced_by; neither
    // is an orphan. Without the cycle-adopt rule, the tree would be empty.
    const items = [
      entry("a", ["b"], ["b"]),
      entry("b", ["a"], ["a"]),
    ];
    expect(pickRoots(items)).toEqual(["a"]);
  });
});

describe("CanvasTree", () => {
  it("renders a flat list when there are no references", () => {
    renderTree([entry("alpha"), entry("beta")]);
    // Each row renders the slug twice (title fallback + subtitle), so
    // use getAllByText to be precise.
    expect(screen.getAllByText("alpha").length).toBeGreaterThan(0);
    expect(screen.getAllByText("beta").length).toBeGreaterThan(0);
  });

  it("hides children until the parent is expanded, then shows them", () => {
    const items = [
      entry("a", ["b"], [], { title: "Alpha" }),
      entry("b", [], ["a"], { title: "Beta" }),
    ];
    renderTree(items);
    expect(screen.queryByText("Beta")).toBeNull();
    const expandButton = screen.getByRole("button", { name: "expand" });
    fireEvent.click(expandButton);
    expect(screen.getByText("Beta")).toBeTruthy();
  });

  it("renders a shared canvas under each parent with a multi-parent badge", () => {
    // a → c, b → c — c is reachable from both. Roots are [a, b]; c appears
    // twice once both parents are expanded.
    const items = [
      entry("a", ["c"], []),
      entry("b", ["c"], []),
      entry("c", [], ["a", "b"]),
    ];
    renderTree(items);
    // Expand both roots.
    const expandButtons = screen.getAllByRole("button", { name: "expand" });
    expandButtons.forEach((btn) => fireEvent.click(btn));
    // c shows up twice — once under each parent.
    const cInstances = screen.getAllByText("c");
    expect(cInstances.length).toBeGreaterThanOrEqual(2);
    // The ↔ multi-parent badge appears.
    expect(screen.getAllByText(/↔ 2/).length).toBeGreaterThan(0);
  });

  it("breaks a cycle with a `↩ cycle` chip without recursing forever", () => {
    // A → B → A. Render adopts 'a' as the root (alphabetical pick in the
    // component containing both). Expanding A reveals B; expanding B
    // reveals A-as-cycle (chip, no further children).
    const items = [
      entry("a", ["b"], ["b"]),
      entry("b", ["a"], ["a"]),
    ];
    renderTree(items);
    // Expand 'a' (the root).
    fireEvent.click(screen.getByRole("button", { name: "expand" }));
    // 'b' now visible under 'a'. Expand it.
    const expandButtons = screen.getAllByRole("button", { name: "expand" });
    const lastBtn = expandButtons[expandButtons.length - 1];
    if (lastBtn) fireEvent.click(lastBtn);
    // The cycle chip is present on the recursive 'a' row.
    expect(screen.getAllByText(/↩ cycle/).length).toBeGreaterThan(0);
    // And the recursion stopped — the cycle row has no expand button of
    // its own (refs are zeroed out when ancestors contain self).
    // We can't count expand buttons exactly because the original 'a'
    // root row may have collapsed-back behaviour, so we just assert the
    // chip is showing.
  });

  it("renders node + edge counts on each row", () => {
    renderTree([entry("solo", [], [], { node_count: 7, edge_count: 12 })]);
    expect(screen.getByText(/7 nodes/)).toBeTruthy();
    expect(screen.getByText(/12 edges/)).toBeTruthy();
  });

  it("links each row to /c/<slug>", () => {
    const { container } = renderTree([entry("xyz", [], [], { title: "X" })]);
    const link = within(container).getByRole("link", { name: /X/ });
    expect(link.getAttribute("href")).toBe("/c/xyz");
  });

  it("shows an empty state when there are no canvases", () => {
    renderTree([]);
    expect(screen.getByText(/No canvases yet/)).toBeTruthy();
  });
});
