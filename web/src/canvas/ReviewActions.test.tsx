/**
 * ReviewActions tests (#324) — the one-click Accept / Reject affordance.
 *
 * Pins: the buttons render only when the selection contains a reviewable
 * (proposed / rejected) node, and a click writes the verdict through the
 * normal update-node path (`canvases.patchNode`) with the human recorded
 * in `review.by` — no dedicated review endpoint.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canvases } from "@/api/canvases";

import { ReviewActions } from "./ReviewActions";

vi.mock("@/api/canvases", () => ({
  canvases: {
    patchNode: vi.fn().mockResolvedValue({}),
  },
}));

const proposed = {
  review: { state: "proposed", by: { kind: "agent", label: "claude" } },
};

function mount(dataById: Record<string, Record<string, unknown>>) {
  return render(
    <ReviewActions
      workspaceSlug="w1"
      nodeIds={Object.keys(dataById)}
      getNodeData={(id) => dataById[id]}
    />,
  );
}

describe("ReviewActions", () => {
  beforeEach(() => {
    vi.mocked(canvases.patchNode).mockClear();
  });

  it("renders nothing when no selected node is reviewable", () => {
    mount({ a: {}, b: { review: { state: "accepted" } } });
    expect(screen.queryByTestId("review-accept")).toBeNull();
    expect(screen.queryByTestId("review-reject")).toBeNull();
  });

  it("shows Accept / Reject for a proposed node", () => {
    mount({ a: proposed });
    expect(screen.getByTestId("review-accept")).toBeTruthy();
    expect(screen.getByTestId("review-reject")).toBeTruthy();
  });

  it("Accept patches data.review with the human verdict", async () => {
    mount({ a: proposed });
    fireEvent.click(screen.getByTestId("review-accept"));
    await waitFor(() => expect(canvases.patchNode).toHaveBeenCalledTimes(1));
    const [slug, id, body] = vi.mocked(canvases.patchNode).mock.calls[0]!;
    expect(slug).toBe("w1");
    expect(id).toBe("a");
    const review = (body as { data: { review: Record<string, unknown> } }).data.review;
    expect(review.state).toBe("accepted");
    expect(review.by).toEqual({ kind: "human", label: "browser" });
  });

  it("Reject patches data.review.state to rejected", async () => {
    mount({ a: proposed });
    fireEvent.click(screen.getByTestId("review-reject"));
    await waitFor(() => expect(canvases.patchNode).toHaveBeenCalledTimes(1));
    const [, , body] = vi.mocked(canvases.patchNode).mock.calls[0]!;
    expect(
      (body as { data: { review: { state: string } } }).data.review.state,
    ).toBe("rejected");
  });

  it("applies the verdict only to reviewable nodes in a mixed selection", async () => {
    mount({ a: proposed, b: {}, c: { review: { state: "rejected" } } });
    fireEvent.click(screen.getByTestId("review-accept"));
    await waitFor(() => expect(canvases.patchNode).toHaveBeenCalledTimes(2));
    const ids = vi.mocked(canvases.patchNode).mock.calls.map((c) => c[1]);
    expect(ids.sort()).toEqual(["a", "c"]);
  });
});
