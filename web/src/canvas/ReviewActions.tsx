/**
 * ReviewActions — one-click Accept / Reject for proposed nodes (#324).
 *
 * Mounted in the selection toolbar when any selected node carries a
 * `data.review` in state "proposed" (or "rejected" — accepting a rejected
 * node reverses the verdict). The verdict is a plain update-node data
 * patch (`reviewVerdictPatch`), so the server, SSE clients, and agents
 * all see it through the normal event stream; the HTTP middleware stamps
 * the event's actor as human/browser and the patch records the human in
 * `review.by`.
 */
import { Check, X } from "lucide-react";

import { canvases } from "@/api/canvases";
import { Button } from "@/components/ui/button";

import { isReviewable, reviewVerdictPatch } from "./review";
import type { MaybeData } from "./placeholder";

type Props = {
  workspaceSlug: string;
  nodeIds: string[];
  getNodeData: (id: string) => MaybeData;
};

export function ReviewActions({ workspaceSlug, nodeIds, getNodeData }: Props) {
  const reviewable = nodeIds.filter((id) => isReviewable(getNodeData(id)));
  if (reviewable.length === 0) return null;

  const applyVerdict = async (state: "accepted" | "rejected") => {
    for (const id of reviewable) {
      try {
        await canvases.patchNode(workspaceSlug, id, {
          data: reviewVerdictPatch(state),
        });
      } catch (err) {
        console.error("review verdict failed", err);
      }
    }
  };

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        data-testid="review-accept"
        title="Accept proposed node"
        aria-label="Accept proposed node"
        className="text-emerald-700 hover:bg-emerald-50"
        onClick={() => void applyVerdict("accepted")}
      >
        <Check className="size-3.5" />
        <span className="text-[11px]">Accept</span>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        data-testid="review-reject"
        title="Reject proposed node"
        aria-label="Reject proposed node"
        className="text-rose-700 hover:bg-rose-50"
        onClick={() => void applyVerdict("rejected")}
      >
        <X className="size-3.5" />
        <span className="text-[11px]">Reject</span>
      </Button>
    </>
  );
}
