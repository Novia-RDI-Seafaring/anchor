/**
 * OrganizeEditor smoke tests.
 *
 * Pins the selection-gated visibility:
 *   - `hasChildren=false` → renders nothing.
 *   - `hasChildren=true`  → renders Vertical / Horizontal / Radial buttons.
 *   - Radial is always disabled until d3-hierarchy lands.
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

  it("clicking Vertical calls the API with orientation='vertical'", async () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren />,
    );
    fireEvent.click(screen.getByRole("button", { name: /vertically/i }));
    await waitFor(() => {
      expect(canvases.organizeSubtree).toHaveBeenCalledWith("w1", "n1", "vertical");
    });
  });

  it("clicking Horizontal calls the API with orientation='horizontal'", async () => {
    render(
      <OrganizeEditor workspaceSlug="w1" nodeId="n1" hasChildren />,
    );
    fireEvent.click(screen.getByRole("button", { name: /horizontally/i }));
    await waitFor(() => {
      expect(canvases.organizeSubtree).toHaveBeenCalledWith("w1", "n1", "horizontal");
    });
  });
});
