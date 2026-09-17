/**
 * ProposalsPanel tests (#359) — one verdict for a whole batch.
 *
 * Pins the panel contract at the component boundary: open and reviewed sets
 * both stay listed, a verdict reaches the API with the right arguments,
 * discarding asks before it removes anything, and hovering a row broadcasts
 * its members so the canvas can ring them.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as proposalSetsApi from "@/api/proposalSets";
import type { ProposalSet } from "@/api/proposalSets";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { ProposalsPanel } from "./ProposalsPanel";

function makeSet(over: Partial<ProposalSet> = {}): ProposalSet {
  return {
    id: "ps1",
    reason: "mindmap of the SoftwareX author guide",
    by: { kind: "agent", label: "claude-code" },
    at: Math.floor(Date.now() / 1000) - 120,
    members: [
      { kind: "node", id: "n1" },
      { kind: "node", id: "n2" },
      { kind: "edge", id: "e1" },
    ],
    state: "open",
    ...over,
  };
}

function reviewResult(set: ProposalSet): proposalSetsApi.ProposalReviewResult {
  return { proposal_set: set, events: set.members.length };
}

function renderPanel(sets: ProposalSet[] = [], error: string | null = null) {
  return render(
    <ProposalsPanel workspaceSlug="plant" sets={sets} error={error} />,
  );
}

function resetStores() {
  useUiStore.setState({
    proposalMemberIds: [],
    proposalHighlightIds: [],
    selectedNodeId: null,
  });
  useCanvasStore.setState({ nodes: {} });
}

beforeEach(resetStores);

afterEach(() => {
  vi.restoreAllMocks();
  resetStores();
});

describe("ProposalsPanel listing", () => {
  it("renders an open set with its reason, proposer, and element count", () => {
    renderPanel([makeSet()]);

    expect(screen.getByText("Proposals (1 open)")).toBeTruthy();
    expect(screen.getByText("mindmap of the SoftwareX author guide")).toBeTruthy();
    expect(screen.getByText(/claude-code · 3 elements/)).toBeTruthy();
    expect(screen.getByTestId("proposal-accept")).toBeTruthy();
    expect(screen.getByTestId("proposal-reject")).toBeTruthy();
  });

  it("keeps reviewed sets listed with their verdict and no action buttons", () => {
    renderPanel([
      makeSet(),
      makeSet({
        id: "ps2",
        reason: "duplicate pump specs",
        state: "rejected",
        discarded: true,
        reviewed_by: { kind: "human", label: "browser" },
        reviewed_at: Math.floor(Date.now() / 1000) - 60,
      }),
      makeSet({
        id: "ps3",
        reason: "valve list",
        state: "accepted",
        reviewed_by: { kind: "human", label: "browser" },
        reviewed_at: Math.floor(Date.now() / 1000) - 30,
      }),
    ]);

    // Only the open one is counted, and only it offers a verdict.
    expect(screen.getByText("Proposals (1 open)")).toBeTruthy();
    expect(screen.getAllByTestId("proposal-row")).toHaveLength(3);
    expect(screen.getAllByTestId("proposal-accept")).toHaveLength(1);

    const verdicts = screen.getAllByTestId("proposal-verdict").map((n) => n.textContent);
    expect(verdicts).toContain("rejected and discarded by browser");
    expect(verdicts).toContain("accepted by browser");
  });

  it("shows an empty hint when the canvas has no sets", () => {
    renderPanel();
    expect(screen.getByText(/no proposal sets yet/)).toBeTruthy();
  });
});

describe("ProposalsPanel verdicts", () => {
  it("accepts a whole set through the review API", async () => {
    const set = makeSet();
    const review = vi
      .spyOn(proposalSetsApi.proposalSets, "review")
      .mockResolvedValue(reviewResult({ ...set, state: "accepted" }));
    renderPanel([set]);

    await act(async () => {
      fireEvent.click(screen.getByTestId("proposal-accept"));
    });

    expect(review).toHaveBeenCalledWith("plant", "ps1", {
      verdict: "accepted",
      discard: false,
    });
  });

  it("rejects without discarding by default", async () => {
    const set = makeSet();
    const review = vi
      .spyOn(proposalSetsApi.proposalSets, "review")
      .mockResolvedValue(reviewResult({ ...set, state: "rejected" }));
    renderPanel([set]);

    await act(async () => {
      fireEvent.click(screen.getByTestId("proposal-reject"));
    });

    expect(review).toHaveBeenCalledWith("plant", "ps1", {
      verdict: "rejected",
      discard: false,
    });
  });

  it("asks for confirmation before discarding, then sends discard", async () => {
    const set = makeSet();
    const review = vi
      .spyOn(proposalSetsApi.proposalSets, "review")
      .mockResolvedValue(reviewResult({ ...set, state: "rejected", discarded: true }));
    renderPanel([set]);

    // The first click only arms the confirmation. Nothing has been removed.
    fireEvent.click(screen.getByTestId("proposal-discard"));
    expect(review).not.toHaveBeenCalled();
    expect(screen.getByTestId("proposal-discard-confirm")).toBeTruthy();
    expect(screen.getByText(/removes 3 elements from the canvas/)).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByTestId("proposal-discard-yes"));
    });
    expect(review).toHaveBeenCalledWith("plant", "ps1", {
      verdict: "rejected",
      discard: true,
    });
  });

  it("cancelling the discard confirmation leaves the set alone", () => {
    const review = vi.spyOn(proposalSetsApi.proposalSets, "review");
    renderPanel([makeSet()]);

    fireEvent.click(screen.getByTestId("proposal-discard"));
    fireEvent.click(screen.getByTestId("proposal-discard-cancel"));

    expect(review).not.toHaveBeenCalled();
    expect(screen.queryByTestId("proposal-discard-confirm")).toBeNull();
    expect(screen.getByTestId("proposal-accept")).toBeTruthy();
  });

  it("surfaces the server's message when a verdict fails", async () => {
    vi.spyOn(proposalSetsApi.proposalSets, "review").mockRejectedValue(
      new Error("proposal set 'ps1' is already accepted"),
    );
    renderPanel([makeSet()]);

    await act(async () => {
      fireEvent.click(screen.getByTestId("proposal-accept"));
    });

    expect(screen.getByTestId("proposals-action-error").textContent).toContain(
      "already accepted",
    );
  });
});

describe("ProposalsPanel canvas coupling", () => {
  it("hovering a row broadcasts its member ids for the canvas marker", () => {
    renderPanel([makeSet()]);
    const row = screen.getByTestId("proposal-row");

    fireEvent.mouseEnter(row);
    expect(useUiStore.getState().proposalHighlightIds).toEqual(["n1", "n2", "e1"]);

    fireEvent.mouseLeave(row);
    expect(useUiStore.getState().proposalHighlightIds).toEqual([]);
  });

  it("clicking a row selects the first member node still on the canvas", () => {
    act(() => {
      // n1 is gone; n2 survives, so the selection lands there.
      useCanvasStore.setState({
        nodes: { n2: { id: "n2", x: 0, y: 0 } as never },
      });
    });
    renderPanel([makeSet()]);

    fireEvent.click(screen.getByTestId("proposal-focus"));
    expect(useUiStore.getState().selectedNodeId).toBe("n2");
  });
});
