/**
 * review.ts helper tests (#324) — pin the data-convention parsing and the
 * verdict patch shape. The patch shape matters because the server
 * deep-merges `data` patches: `by` must carry BOTH kind and label so the
 * proposing agent's identity is fully replaced, never half-merged.
 */
import { describe, expect, it } from "vitest";

import {
  isReviewable,
  reviewState,
  reviewVerdictPatch,
} from "./review";

describe("reviewState", () => {
  it("returns null state for missing / empty / non-object review", () => {
    expect(reviewState(undefined).state).toBeNull();
    expect(reviewState({}).state).toBeNull();
    expect(reviewState({ review: "accepted" }).state).toBeNull();
    expect(reviewState({ review: ["proposed"] }).state).toBeNull();
  });

  it("parses each valid state", () => {
    for (const s of ["proposed", "accepted", "rejected"] as const) {
      expect(reviewState({ review: { state: s } }).state).toBe(s);
    }
  });

  it("ignores an unknown state value", () => {
    expect(reviewState({ review: { state: "maybe" } }).state).toBeNull();
  });

  it("surfaces the proposer's label", () => {
    const r = reviewState({
      review: { state: "proposed", by: { kind: "agent", label: "claude" } },
    });
    expect(r.byLabel).toBe("claude");
  });
});

describe("isReviewable", () => {
  it("is true for proposed and rejected, false otherwise", () => {
    expect(isReviewable({ review: { state: "proposed" } })).toBe(true);
    expect(isReviewable({ review: { state: "rejected" } })).toBe(true);
    expect(isReviewable({ review: { state: "accepted" } })).toBe(false);
    expect(isReviewable({})).toBe(false);
  });
});

describe("reviewVerdictPatch", () => {
  it("records the human with a complete by object (deep-merge safe)", () => {
    const patch = reviewVerdictPatch("accepted");
    expect(patch.review.state).toBe("accepted");
    // Both keys present — a partial {kind} patch would deep-merge into
    // {kind: "human", label: "<agent>"} on the server.
    expect(patch.review.by).toEqual({ kind: "human", label: "browser" });
    expect(typeof patch.review.at).toBe("number");
  });

  it("supports the rejected verdict", () => {
    expect(reviewVerdictPatch("rejected").review.state).toBe("rejected");
  });
});
