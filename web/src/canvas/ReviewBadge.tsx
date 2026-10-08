/**
 * ReviewBadge — the quiet violet ring round an element that belongs to an
 * open proposal set (#359).
 *
 * It used to also print a "◇ proposed · <agent>" / "✕ rejected" chip from
 * the element's own `data.review` (#324). That chip is gone from the
 * canvas: the verdict on a change now lives with the change -- under the
 * ghost, in the intent thread -- and a per-element stamp left over from an
 * earlier round read as the element's status long after it stopped being
 * one. "✕ rejected" over a card the reader had since accepted through a
 * later proposal was the case that settled it. The stamp itself is still
 * written and read (accept / reject in the toolbar, `reviewState`); it is
 * just no longer worn on the card.
 *
 * Proposal sets are a different thing: membership of a batch someone will
 * judge as one thing. That lives in canvas metadata, not on the element, and
 * arrives here through uiStore. The ring says "part of what Accept all is
 * about to touch"; hovering the set in the Proposals panel strengthens it.
 */
import { useUiStore } from "@/stores/uiStore";

import { REVIEW_PROPOSED_COLOR } from "./review";
import type { MaybeData } from "./placeholder";

export function ReviewBadge({
  nodeId,
}: {
  /** Kept for the callers' sake; the element's own review stamp is not shown. */
  data?: MaybeData;
  /** The element's id. Without it the proposal-set marker cannot apply. */
  nodeId?: string;
}) {
  // Selecting a boolean, not the array: an identical membership list after a
  // refetch then costs a selector run and no re-render.
  const inOpenSet = useUiStore((s) =>
    nodeId ? s.proposalMemberIds.includes(nodeId) : false,
  );
  const highlighted = useUiStore((s) =>
    nodeId ? s.proposalHighlightIds.includes(nodeId) : false,
  );
  if (!inOpenSet && !highlighted) return null;
  return (
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
  );
}
