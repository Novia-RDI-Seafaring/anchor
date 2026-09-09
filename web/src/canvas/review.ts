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
 * plain update-node data patch. Visual language: proposed gets a quiet
 * violet chip (distinct from the placeholder's sky-blue "empty" signal);
 * rejected keeps its badge and renders dimmed — never hidden, because a
 * rejection is feedback the agent must still be able to read. Accepted
 * nodes drop the badge entirely.
 *
 * One tiny module (mirroring placeholder.ts) so the badge, the toolbar
 * actions, and the graph-level dimming can't drift apart.
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

/** Violet-500 — the proposed-badge accent (placeholders own sky-blue). */
export const REVIEW_PROPOSED_COLOR = "rgb(139, 92, 246)";
/** Rose-500 — the rejected-badge accent. */
export const REVIEW_REJECTED_COLOR = "rgb(244, 63, 94)";
/** Opacity applied to a rejected node's whole body (dimmed, not hidden). */
export const REVIEW_REJECTED_OPACITY = 0.45;
