/**
 * ProposalsPanel — one verdict for everything an agent added in one go (#359).
 *
 * A FilesExplorer tab listing the canvas's proposal sets: open ones at the
 * top, newest first, each showing why the batch was proposed, who proposed it,
 * how many elements it covers and how long it has waited. An open set gets
 * "Accept all" and "Reject all". Discarding is offered underneath as the
 * secondary action, because it removes the elements from the canvas instead of
 * stamping them, and it asks first.
 *
 * Reviewed sets stay listed and go quiet, so a human can see what they already
 * decided. A discarded rejection is the only trace left of the elements it
 * removed, which is why the row says so in words.
 *
 * Data comes in through props from `useProposalSetsFeed` (mounted by
 * FilesExplorer so the tab badge shares the same feed); mutations go out
 * through the proposal-sets API, whose `anchor:proposal-sets-changed` nudge
 * makes the feed refetch. Visual language matches the other shell panels:
 * small uppercase headers, bordered rows, neutral palette, dense type.
 */
import { useEffect, useState } from "react";

import {
  errorDetail,
  proposalSets,
  type ProposalSet,
  type ProposalVerdict,
} from "@/api/proposalSets";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import { timeAgo } from "./intentsFeed";
import { actorName, elementCount, verdictLine } from "./proposalSetsFeed";

type Props = {
  workspaceSlug: string;
  sets: ProposalSet[];
  error: string | null;
};

export function ProposalsPanel({ workspaceSlug, sets, error }: Props) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const openCount = sets.filter((s) => s.state === "open").length;

  const review = async (
    set: ProposalSet,
    verdict: ProposalVerdict,
    discard = false,
  ) => {
    if (busyId) return;
    setBusyId(set.id);
    try {
      await proposalSets.review(workspaceSlug, set.id, { verdict, discard });
      setActionError(null);
    } catch (e) {
      setActionError(errorDetail(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div
      className="flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden bg-white"
      data-testid="proposals-panel"
    >
      <div className="flex items-baseline justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          Proposals ({openCount} open)
        </span>
        <span className="text-[9px] italic text-neutral-400">one verdict per batch</span>
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-1.5">
        {error ? (
          <div className="px-2 text-[10px] text-red-600">error: {error}</div>
        ) : null}
        {actionError ? (
          <div
            className="px-2 text-[10px] text-red-600"
            data-testid="proposals-action-error"
          >
            error: {actionError}
          </div>
        ) : null}

        {sets.length === 0 ? (
          <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
            no proposal sets yet — an agent groups what it adds so you can
            review it in one go
          </div>
        ) : (
          sets.map((set) => (
            <ProposalRow
              key={set.id}
              set={set}
              busy={busyId === set.id}
              onReview={(verdict, discard) => void review(set, verdict, discard)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProposalRow — one set. Hovering rings its members on the canvas; clicking
// selects the first member that is still there.
// ---------------------------------------------------------------------------

function ProposalRow({
  set,
  busy,
  onReview,
}: {
  set: ProposalSet;
  busy: boolean;
  onReview: (verdict: ProposalVerdict, discard: boolean) => void;
}) {
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const setHighlightIds = useUiStore((s) => s.setProposalHighlightIds);
  const setSelectedNodeId = useUiStore((s) => s.setSelectedNodeId);

  const isOpen = set.state === "open";
  const ids = set.members.map((m) => m.id);
  const when = timeAgo(isOpen ? set.at : set.reviewed_at ?? set.at);

  // A row that unmounts mid-hover (a verdict removes it from the open group,
  // a refetch reorders the list) would otherwise leave its ring on the canvas
  // with no pointer anywhere near it.
  useEffect(() => () => setHighlightIds([]), [setHighlightIds]);

  /**
   * Select the first member node still on the canvas.
   *
   * Fitting the viewport to the whole set is not cheap from here: this panel
   * lives in the left explorer, outside the ReactFlowProvider CanvasShell
   * mounts, so it cannot call `useReactFlow().fitView` the way CatchUpPanel
   * does from inside the canvas. Selecting goes through the same uiStore slot
   * CatchUpPanel uses, and the hover ring is what actually shows the set as a
   * whole, so the cheap half is the useful half.
   */
  const focusMembers = () => {
    const nodes = useCanvasStore.getState().nodes;
    const first = set.members.find((m) => m.kind === "node" && nodes[m.id]);
    if (first) setSelectedNodeId(first.id);
  };

  return (
    <div
      className={cn(
        "rounded border px-2 py-1.5 text-xs",
        isOpen
          ? "border-violet-200 bg-violet-50/50"
          : "border-neutral-200 bg-white",
      )}
      data-testid="proposal-row"
      data-set-id={set.id}
      data-state={set.state}
      onMouseEnter={() => setHighlightIds(ids)}
      onMouseLeave={() => setHighlightIds([])}
    >
      <button
        type="button"
        onClick={focusMembers}
        data-testid="proposal-focus"
        className="block w-full text-left"
        title="Select this set's first element on the canvas"
      >
        <div className="flex items-start gap-1.5">
          <span
            className={cn(
              "mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full",
              isOpen
                ? "bg-violet-500"
                : set.state === "accepted"
                  ? "bg-green-500"
                  : "bg-rose-400",
            )}
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <div
              className={cn(
                "break-words font-medium",
                isOpen ? "text-neutral-800" : "text-neutral-500",
              )}
            >
              {set.reason || "untitled proposal"}
            </div>
            <div className="mt-0.5 truncate text-[10px] text-neutral-500">
              {actorName(set.by)} · {elementCount(set.members.length)}
              {when ? ` · ${when}` : ""}
            </div>
          </div>
        </div>
      </button>

      {isOpen ? (
        confirmDiscard ? (
          <div className="mt-1.5 space-y-1" data-testid="proposal-discard-confirm">
            <div className="text-[10px] text-rose-700">
              Discard removes {elementCount(set.members.length)} from the canvas.
              This cannot be undone.
            </div>
            <div className="flex gap-1">
              <RowButton
                label="Yes, discard"
                tone="danger"
                disabled={busy}
                testId="proposal-discard-yes"
                onClick={() => onReview("rejected", true)}
              />
              <RowButton
                label="Cancel"
                disabled={busy}
                testId="proposal-discard-cancel"
                onClick={() => setConfirmDiscard(false)}
              />
            </div>
          </div>
        ) : (
          <div className="mt-1.5 space-y-1">
            <div className="flex gap-1">
              <RowButton
                label="Accept all"
                disabled={busy}
                testId="proposal-accept"
                onClick={() => onReview("accepted", false)}
              />
              <RowButton
                label="Reject all"
                disabled={busy}
                testId="proposal-reject"
                onClick={() => onReview("rejected", false)}
              />
            </div>
            <button
              type="button"
              onClick={() => setConfirmDiscard(true)}
              disabled={busy}
              data-testid="proposal-discard"
              className="text-[10px] text-neutral-500 underline decoration-dotted underline-offset-2 hover:text-rose-700 disabled:cursor-default disabled:opacity-40"
              title="Reject and remove these elements from the canvas"
            >
              Reject and discard the elements
            </button>
          </div>
        )
      ) : (
        <div
          className="mt-0.5 pl-3 text-[10px] italic text-neutral-400"
          data-testid="proposal-verdict"
        >
          {verdictLine(set)}
        </div>
      )}
    </div>
  );
}

function RowButton({
  label,
  onClick,
  disabled,
  testId,
  tone,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  testId: string;
  tone?: "danger";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
      className={cn(
        "rounded border px-2 py-0.5 text-[10px] font-medium disabled:cursor-default disabled:opacity-40",
        tone === "danger"
          ? "border-rose-300 bg-white text-rose-700 hover:bg-rose-50"
          : "border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-100",
      )}
    >
      {label}
    </button>
  );
}
