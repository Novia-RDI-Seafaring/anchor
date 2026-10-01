/**
 * refReview.ts — a person's verdict on one source reference.
 *
 * Distinct from `evidence`, and deliberately so. Evidence is the server
 * saying "this claim still matches the cell it came from": machine-owned,
 * recomputed on every write, and a caller's own verdict is stripped at the
 * write seam. This is a person saying "I looked at the source, and this
 * reference is right" -- or "it points at the wrong field".
 *
 * They can disagree, and the disagreement is the most useful state in the
 * system: machine-verified but rejected by a reader means the extraction
 * matched something real and still took the wrong thing. One field could not
 * express that, and storing the human verdict where the server recomputes
 * would erase it on the next edit.
 *
 * The words are the ones the canvas already uses for node review (#324), not
 * a second vocabulary for the same idea one level down:
 *
 *   (absent)   nobody has looked yet
 *   accepted   a reader checked the source and it is right
 *   rejected   a reader checked the source and it is wrong
 *
 * A note rides along, because "wrong" without "wrong how" leaves whoever
 * reads it next with only the disagreement and none of the reason.
 */
import type { ReviewStateName } from "./review";

export type RefVerdictName = Extract<ReviewStateName, "accepted" | "rejected">;

export type RefReview = {
  state: RefVerdictName;
  by?: { kind: "human" | "agent" | "system"; label?: string };
  at?: number;
  /** Why, in the reader's words. "Wrong field", "off by a row", "this is J2". */
  note?: string;
};

/** Read a verdict off a spec row, or null when nobody has judged it. */
export function refReview(row: unknown): RefReview | null {
  if (typeof row !== "object" || row === null) return null;
  const raw = (row as Record<string, unknown>).review;
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  if (r.state !== "accepted" && r.state !== "rejected") return null;
  const by = typeof r.by === "object" && r.by !== null ? (r.by as RefReview["by"]) : undefined;
  return {
    state: r.state,
    by,
    at: typeof r.at === "number" ? r.at : undefined,
    note: typeof r.note === "string" && r.note.trim() ? r.note.trim() : undefined,
  };
}

/**
 * The verdict to store, or `null` to clear one.
 *
 * Clearing matters: a reader who judged in haste, or whose objection has been
 * fixed, needs a way back to "nobody has looked". Without it the only way out
 * of a wrong verdict is the opposite wrong verdict.
 *
 * `by` carries kind AND label together, so a merge replaces the previous
 * reviewer's identity outright rather than leaving half of each.
 */
export function refVerdict(
  state: RefVerdictName | null,
  note?: string,
): { review: RefReview | null } {
  if (state === null) return { review: null };
  const trimmed = (note ?? "").trim();
  return {
    review: {
      state,
      by: { kind: "human", label: "browser" },
      at: Date.now() / 1000,
      ...(trimmed ? { note: trimmed } : {}),
    },
  };
}

/** Emerald-600 — checked and right. Matches the verified value tint. */
export const REF_ACCEPTED_COLOR = "rgb(5, 150, 105)";
/** Rose-500 — checked and wrong. The same rose a rejected node carries. */
export const REF_REJECTED_COLOR = "rgb(244, 63, 94)";
