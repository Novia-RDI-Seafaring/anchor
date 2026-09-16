/**
 * proposalSetsFeed helper tests (#359) — the pure half of the Proposals feed.
 *
 * Ordering is load-bearing: a human opening the panel should see what is
 * waiting on them, newest first, above what they already decided.
 */
import { describe, expect, it } from "vitest";

import type { ProposalSet } from "@/api/proposalSets";

import {
  actorName,
  elementCount,
  memberIds,
  sortProposalSets,
  verdictLine,
} from "./proposalSetsFeed";

function makeSet(over: Partial<ProposalSet> = {}): ProposalSet {
  return {
    id: "ps1",
    reason: "a batch",
    by: { kind: "agent", label: "claude-code" },
    at: 100,
    members: [{ kind: "node", id: "n1" }],
    state: "open",
    ...over,
  };
}

describe("sortProposalSets", () => {
  it("puts open sets first, newest first inside each group", () => {
    const ordered = sortProposalSets([
      makeSet({ id: "old-open", at: 100 }),
      makeSet({ id: "new-done", at: 400, state: "accepted" }),
      makeSet({ id: "new-open", at: 300 }),
      makeSet({ id: "old-done", at: 50, state: "rejected" }),
    ]);
    expect(ordered.map((s) => s.id)).toEqual([
      "new-open",
      "old-open",
      "new-done",
      "old-done",
    ]);
  });

  it("does not mutate the list it was given", () => {
    const input = [makeSet({ id: "a", at: 1 }), makeSet({ id: "b", at: 2 })];
    sortProposalSets(input);
    expect(input.map((s) => s.id)).toEqual(["a", "b"]);
  });
});

describe("memberIds", () => {
  it("collects node and edge ids across sets, de-duplicated", () => {
    const ids = memberIds([
      makeSet({
        id: "a",
        members: [
          { kind: "node", id: "n1" },
          { kind: "edge", id: "e1" },
        ],
      }),
      makeSet({
        id: "b",
        members: [
          { kind: "node", id: "n1" },
          { kind: "node", id: "n2" },
        ],
      }),
    ]);
    expect(ids).toEqual(["n1", "e1", "n2"]);
  });
});

describe("labels", () => {
  it("names an actor by label, falling back to kind", () => {
    expect(actorName({ kind: "agent", label: "claude-code" })).toBe("claude-code");
    expect(actorName({ kind: "system" })).toBe("system");
    expect(actorName(undefined)).toBe("unknown");
  });

  it("counts elements in singular and plural", () => {
    expect(elementCount(1)).toBe("1 element");
    expect(elementCount(4)).toBe("4 elements");
  });

  it("says when a rejection also removed the elements", () => {
    const reviewed_by = { kind: "human" as const, label: "browser" };
    expect(verdictLine(makeSet({ state: "accepted", reviewed_by }))).toBe(
      "accepted by browser",
    );
    expect(verdictLine(makeSet({ state: "rejected", reviewed_by }))).toBe(
      "rejected by browser",
    );
    expect(
      verdictLine(makeSet({ state: "rejected", discarded: true, reviewed_by })),
    ).toBe("rejected and discarded by browser");
    expect(verdictLine(makeSet({ state: "open" }))).toBe("");
  });
});
