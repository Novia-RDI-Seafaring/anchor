/**
 * OrganizeEditor smoke tests.
 *
 * Pins the selection-gated visibility:
 *   - `hasChildren=false` → renders nothing.
 *   - `hasChildren=true`  → renders Vertical / Horizontal / Radial buttons.
 *   - Radial is always disabled until d3-hierarchy lands.
 *
 * Also covers the direction selector (↓ outgoing / ↑ incoming / ↔ any) — the
 * fix for the acme-org "CFO drags CEO in" bug. Default direction is "any" so
 * existing UX is preserved.
 *
 * The click handlers hit `canvases.organizeSubtree`, which is mocked here so
 * the test stays offline. We assert the API was called with the right args
 * but stop short of asserting SSE — that's covered by the canvasStore tests
 * and the Python end-to-end test in `tests/core/test_workspace_organize.py`.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/canvases", () => ({
  canvases: {
    organizeSubtree: vi.fn(async () => ({ moves: [], event_count: 0 })),
  },
}));

import { canvases } from "@/api/canvases";

import { OrganizeEditor } from "./OrganizeEditor";

describe("OrganizeEditor", () => {
  it("renders nothing when the node has no children", () => {
    const { container } = render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders Vertical / Horizontal / Radial buttons when the node has children", () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren />,
    );
    expect(screen.getByRole("button", { name: /vertically/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /horizontally/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /radial/i })).toBeTruthy();
  });

  it("radial button is disabled (coming-soon)", () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren />,
    );
    const radial = screen.getByRole("button", { name: /radial/i }) as HTMLButtonElement;
    expect(radial.disabled).toBe(true);
  });

  it("clicking Vertical calls the API with orientation='vertical' and default direction='any'", async () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren />,
    );
    fireEvent.click(screen.getByRole("button", { name: /vertically/i }));
    await waitFor(() => {
      // Default direction is "any" — preserves v1 undirected behaviour.
      expect(canvases.organizeSubtree).toHaveBeenCalledWith(
        "w1", "n1", "vertical", "dagre", "any",
      );
    });
  });

  it("clicking Horizontal calls the API with orientation='horizontal' and default direction='any'", async () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren />,
    );
    fireEvent.click(screen.getByRole("button", { name: /horizontally/i }));
    await waitFor(() => {
      expect(canvases.organizeSubtree).toHaveBeenCalledWith(
        "w1", "n1", "horizontal", "dagre", "any",
      );
    });
  });

  it("picking direction='incoming' is forwarded to the API", async () => {
    // The acme-org case: user picks ↑ then clicks Vertical, expecting strict
    // descendant scoping (reports-to convention).
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="cfo" hasChildren />,
    );
    fireEvent.click(screen.getByRole("radio", { name: /Incoming/i }));
    fireEvent.click(screen.getByRole("button", { name: /vertically/i }));
    await waitFor(() => {
      expect(canvases.organizeSubtree).toHaveBeenCalledWith(
        "w1", "cfo", "vertical", "dagre", "incoming",
      );
    });
  });

  it("picking direction='outgoing' is forwarded to the API", async () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="root" hasChildren />,
    );
    fireEvent.click(screen.getByRole("radio", { name: /Outgoing/i }));
    fireEvent.click(screen.getByRole("button", { name: /vertically/i }));
    await waitFor(() => {
      expect(canvases.organizeSubtree).toHaveBeenCalledWith(
        "w1", "root", "vertical", "dagre", "outgoing",
      );
    });
  });

  it("direction radio group shows three options with the ↓ ↑ ↔ glyphs", () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren />,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    const glyphs = radios.map((r) => r.textContent);
    expect(glyphs).toEqual(["↓", "↑", "↔"]);
    // "Any" is selected by default.
    const any = screen.getByRole("radio", { name: /Any/i });
    expect(any.getAttribute("aria-checked")).toBe("true");
  });
});
