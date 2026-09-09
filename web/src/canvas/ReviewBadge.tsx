/**
 * ReviewBadge — small "◇ proposed · <agent>" / "✕ rejected" chip (#324).
 *
 * Renders at the top-LEFT corner of a primitive (the placeholder chip owns
 * the top-right), matching its visual language: white pill, tiny italic
 * text, colored per state. Only `proposed` and `rejected` render a badge —
 * `accepted` is the clean, unmarked state. The verdict itself is written
 * by the selection toolbar's Accept / Reject actions via a plain
 * update-node patch.
 */
import {
  REVIEW_PROPOSED_COLOR,
  REVIEW_REJECTED_COLOR,
  reviewState,
} from "./review";
import type { MaybeData } from "./placeholder";

export function ReviewBadge({ data }: { data: MaybeData }) {
  const { state, byLabel } = reviewState(data);
  if (state !== "proposed" && state !== "rejected") return null;
  const proposed = state === "proposed";
  const color = proposed ? REVIEW_PROPOSED_COLOR : REVIEW_REJECTED_COLOR;
  return (
    <div
      data-testid="review-badge"
      data-review-state={state}
      className="pointer-events-none absolute -top-2.5 left-2 z-10 rounded-full bg-white px-1.5 py-0.5 text-[10px] italic shadow-sm"
      style={{ color, borderColor: color, borderWidth: 1 }}
    >
      <span aria-hidden>{proposed ? "◇" : "✕"}</span> {state}
      {proposed && byLabel ? ` · ${byLabel}` : ""}
    </div>
  );
}
