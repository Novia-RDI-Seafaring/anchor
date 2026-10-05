/**
 * A person's verdict on one source reference — distinct from `evidence`,
 * which is the server saying a claim still matches its cell.
 */
import { describe, expect, it } from "vitest";

import { refReview, refVerdict } from "@/canvas/refReview";

describe("refReview", () => {
  it("reads a verdict off a row", () => {
    const got = refReview({ review: { state: "rejected", note: "wrong field", at: 5 } });
    expect(got).toMatchObject({ state: "rejected", note: "wrong field", at: 5 });
  });

  it("returns nothing for a row nobody has judged", () => {
    expect(refReview({ key: "B", value: "87" })).toBeNull();
    expect(refReview(null)).toBeNull();
    expect(refReview({ review: null })).toBeNull();
  });

  it("refuses a state it does not recognise rather than showing a mystery chip", () => {
    expect(refReview({ review: { state: "proposed" } })).toBeNull();
    expect(refReview({ review: { state: "maybe" } })).toBeNull();
  });

  it("treats a blank note as no note", () => {
    expect(refReview({ review: { state: "accepted", note: "   " } })?.note).toBeUndefined();
  });
});

describe("refVerdict", () => {
  it("records who judged and when, alongside the verdict", () => {
    const { review } = refVerdict("accepted");
    expect(review).toMatchObject({ state: "accepted", by: { kind: "human" } });
    expect(typeof review!.at).toBe("number");
  });

  it("carries the reason, because 'wrong' without 'wrong how' helps nobody", () => {
    expect(refVerdict("rejected", "points at J2").review!.note).toBe("points at J2");
  });

  it("clears back to unjudged", () => {
    // A reader who judged in haste, or whose objection was fixed, needs a way
    // back. Otherwise the only way out of a wrong verdict is the opposite one.
    expect(refVerdict(null).review).toBeNull();
  });

  it("names the reviewer's kind and label together", () => {
    // A partial {kind} patch would merge over the previous reviewer and leave
    // half of each identity behind.
    const by = refVerdict("accepted").review!.by!;
    expect(by.kind).toBe("human");
    expect(typeof by.label).toBe("string");
  });

  it("drops a whitespace-only note instead of storing an empty reason", () => {
    expect(refVerdict("rejected", "  ").review!.note).toBeUndefined();
  });
});
