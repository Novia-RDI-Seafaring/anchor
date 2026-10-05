/**
 * review.ts — shared helpers for the node review-state convention (#324).
 *
 * A reviewed node carries `data.review`:
 *
 *   {state: "proposed" | "accepted" | "rejected",
 *    by?: {kind, label?}, at?: <unix ts>}
 *
 * The server stamps `proposed` on agent-created nodes in review-mode
 * workspaces (`metadata.review_mode == true`); humans accept/reject via a
 * plain update-node data patch. The stamp is no longer worn on the card:
 * no chip, no dimming. The verdict on a change lives with the change, under
 * its ghost in the intent thread, and a per-element stamp left from an
 * earlier round read as the element's status long after it stopped being
 * one. The toolbar actions and the panels still read and write it.
 *
 * One tiny module (mirroring placeholder.ts) so the readers and writers of
 * the stamp can't drift apart.
 */
import type { MaybeData } from "./placeholder";

export type ReviewStateName = "proposed" | "accepted" | "rejected";

export type ReviewState = {
  /** The review state, or null when the node has no (valid) review object. */
  state: ReviewStateName | null;
  /** Display label of whoever set the state (e.g. the proposing agent). */
  byLabel: string;
};

const STATES: readonly string[] = ["proposed", "accepted", "rejected"];

/** Read the review state from a node's `data` payload. */
export function reviewState(data: MaybeData): ReviewState {
  const d = (data ?? {}) as Record<string, unknown>;
  const review = d.review;
  if (typeof review !== "object" || review === null || Array.isArray(review)) {
    return { state: null, byLabel: "" };
  }
  const r = review as Record<string, unknown>;
  const state = typeof r.state === "string" && STATES.includes(r.state)
    ? (r.state as ReviewStateName)
    : null;
  const by = r.by;
  const byLabel =
    typeof by === "object" && by !== null && typeof (by as Record<string, unknown>).label === "string"
      ? ((by as Record<string, unknown>).label as string)
      : "";
  return { state, byLabel };
}

/**
 * The `data` patch that records a human verdict via the normal
 * update-node path. The `by` object carries BOTH `kind` and `label` so the
 * server's deep-merge fully replaces the proposing agent's identity —
 * a partial `{kind: "human"}` patch would keep the agent's label and
 * produce a half-merged hybrid.
 */
export function reviewVerdictPatch(
  state: Extract<ReviewStateName, "accepted" | "rejected">,
): { review: { state: ReviewStateName; by: { kind: "human"; label: string }; at: number } } {
  return {
    review: {
      state,
      by: { kind: "human", label: "browser" },
      at: Date.now() / 1000,
    },
  };
}

/** True when the toolbar should offer Accept / Reject for this node. */
export function isReviewable(data: MaybeData): boolean {
  const s = reviewState(data).state;
  return s === "proposed" || s === "rejected";
}

/** Violet-500 — the proposal-set ring accent (placeholders own sky-blue). */
export const REVIEW_PROPOSED_COLOR = "rgb(139, 92, 246)";
