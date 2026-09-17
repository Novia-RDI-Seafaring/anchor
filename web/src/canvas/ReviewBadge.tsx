/**
 * ReviewBadge — small "◇ proposed · <agent>" / "✕ rejected" chip (#324),
 * extended with proposal-set membership (#359).
 *
 * Renders at the top-LEFT corner of a primitive (the placeholder chip owns
 * the top-right), matching its visual language: white pill, tiny italic
 * text, colored per state. Only `proposed` and `rejected` render a badge —
 * `accepted` is the clean, unmarked state. The verdict itself is written
 * by the selection toolbar's Accept / Reject actions via a plain
 * update-node patch.
 *
 * Proposal sets add a second reason an element is under review: it belongs to
 * a batch someone will judge as one thing. That lives in canvas metadata, not
 * on the element, so it arrives here through uiStore rather than through
 * `data`. It gets the same chip rather than a second one, plus a quiet violet
 * ring around the element so a whole set reads as a group. Hovering the set in
 * the Proposals panel strengthens the ring, which is how a human sees what a
 * single "Accept all" is about to touch.
 */
import { useUiStore } from "@/stores/uiStore";

import {
  REVIEW_PROPOSED_COLOR,
  REVIEW_REJECTED_COLOR,
  reviewState,
} from "./review";
import type { MaybeData } from "./placeholder";

export function ReviewBadge({
  data,
  nodeId,
}: {
  data: MaybeData;
  /** The element's id. Without it the proposal-set marker cannot apply. */
  nodeId?: string;
}) {
  const { state, byLabel } = reviewState(data);
  // Selecting a boolean, not the array: an identical membership list after a
  // refetch then costs a selector run and no re-render.
  const inOpenSet = useUiStore((s) =>
    nodeId ? s.proposalMemberIds.includes(nodeId) : false,
  );
  const highlighted = useUiStore((s) =>
    nodeId ? s.proposalHighlightIds.includes(nodeId) : false,
  );

  const proposed = state === "proposed";
  const rejected = state === "rejected";
  // A member with no per-element review stamp still needs to say why it is
  // ringed, so it borrows the proposed chip with its own wording.
  const showChip = proposed || rejected || inOpenSet;
  const showRing = inOpenSet || highlighted;
  if (!showChip && !showRing) return null;

  const color = rejected ? REVIEW_REJECTED_COLOR : REVIEW_PROPOSED_COLOR;
  const chipText = proposed || rejected ? state : "proposal set";

  return (
    <>
      {showRing ? (
        <div
          data-testid="proposal-member-ring"
          data-highlighted={highlighted ? "true" : "false"}
          aria-hidden="true"
          className="pointer-events-none absolute -inset-[3px] rounded-lg"
          style={{
            boxShadow: `0 0 0 ${highlighted ? 2 : 1}px ${REVIEW_PROPOSED_COLOR}`,
            opacity: highlighted ? 0.9 : 0.35,
          }}
        />
      ) : null}
      {showChip ? (
        <div
          data-testid="review-badge"
          data-review-state={state ?? "set-member"}
          className="pointer-events-none absolute -top-2.5 left-2 z-10 rounded-full bg-white px-1.5 py-0.5 text-[10px] italic shadow-sm"
          style={{ color, borderColor: color, borderWidth: 1 }}
        >
          <span aria-hidden>{rejected ? "✕" : "◇"}</span> {chipText}
          {proposed && byLabel ? ` · ${byLabel}` : ""}
        </div>
      ) : null}
    </>
  );
}
