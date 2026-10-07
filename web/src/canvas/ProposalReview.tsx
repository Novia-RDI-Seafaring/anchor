import { useEffect, useMemo, useState } from "react";

import type { ResolvableRef } from "@/api/documents";
import { proposalSets, type ProposalSet } from "@/api/proposalSets";
import {
  changeCount,
  diffNodeData,
  onlyGeometry,
  type NodeDiff,
  type RowChange,
} from "@/canvas/nodeDiff";
import { SourceAnchorButton } from "@/canvas/SourceAnchorButton";
import { useCanvasStore } from "@/stores/canvasStore";

/**
 * ProposalReview — judge a change against what it replaced.
 *
 * A ring round a card tells you something was touched. It does not tell you
 * whether to accept it: a retitled card looks fine either way until you can
 * see what the title was. So this shows the pair, with the parts that differ
 * lit, and the verdict buttons beside them.
 *
 * The rows are rendered rather than printed, and they keep their anchors. The
 * whole point of reviewing a change to grounded data is being able to open the
 * source and check -- a diff that reduced a spec to two columns of text would
 * take away the one thing that makes the judgement possible.
 *
 * One changed value reads inline, old struck through and new beside it, the
 * way a tracked change does. Several read side by side. The count decides, so
 * the reader is never asked to pick a view.
 */

const INLINE_LIMIT = 2;

export function ProposalReview({
  workspaceSlug,
  setId,
  onClose,
}: {
  workspaceSlug: string;
  setId: string;
  onClose: () => void;
}) {
  const [record, setRecord] = useState<ProposalSet | null>(null);
  const [busy, setBusy] = useState(false);
  const nodes = useCanvasStore((s) => s.nodes);

  useEffect(() => {
    let cancelled = false;
    void proposalSets
      .list(workspaceSlug)
      .then((sets) => {
        if (!cancelled) setRecord(sets.find((s) => s.id === setId) ?? null);
      })
      .catch(() => {
        if (!cancelled) setRecord(null);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceSlug, setId]);

  const members = useMemo(() => {
    if (!record) return [];
    return record.members
      .filter((m) => m.kind === "node")
      .map((m) => {
        const node = nodes[m.id];
        const before = (m as { before?: Record<string, unknown> }).before ?? null;
        const after = (node?.data ?? {}) as Record<string, unknown>;
        return { id: m.id, before, after, node, diff: diffNodeData(before, after) };
      });
  }, [record, nodes]);

  if (!record) return null;

  const verdict = async (state: "accepted" | "rejected", discard = false) => {
    setBusy(true);
    try {
      await proposalSets.review(workspaceSlug, setId, { verdict: state, discard });
      onClose();
    } catch (err) {
      window.alert(
        `Could not record the verdict: ${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="proposal-review"
      className="absolute inset-y-4 right-4 z-40 flex w-[min(40rem,60vw)] flex-col overflow-hidden rounded-lg border border-violet-300 bg-white shadow-2xl"
    >
      <div className="flex items-start justify-between gap-2 border-b border-neutral-200 bg-violet-50 px-3 py-2">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-violet-700">
            Proposal · {record.state}
          </div>
          {/* What was asked comes first: a change is judged against the ask,
              not in isolation. */}
          <p className="mt-0.5 text-[12px] leading-snug text-neutral-700">{record.reason}</p>
          <div className="mt-0.5 text-[10px] text-neutral-500">
            by {record.by?.label ?? record.by?.kind ?? "someone"}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close review"
          className="rounded px-1.5 py-0.5 text-neutral-500 hover:bg-neutral-200"
        >
          ✕
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
        {members.map((m) => (
          <MemberDiff
            key={m.id}
            id={m.id}
            diff={m.diff}
            before={m.before}
            after={m.after}
            workspaceSlug={workspaceSlug}
          />
        ))}
      </div>

      {record.state === "open" ? (
        <div className="flex items-center gap-2 border-t border-neutral-200 bg-neutral-50 px-3 py-2">
          <button
            type="button"
            data-testid="proposal-accept"
            disabled={busy}
            onClick={() => verdict("accepted")}
            className="rounded bg-emerald-600 px-2.5 py-1 text-[12px] text-white hover:bg-emerald-700 disabled:bg-neutral-300"
          >
            Accept
          </button>
          {/* Declining a change puts back what it replaced, which is why the
              button can say so plainly rather than warning about deletion. */}
          <button
            type="button"
            data-testid="proposal-decline"
            disabled={busy}
            onClick={() => verdict("rejected", true)}
            className="rounded border border-rose-300 px-2.5 py-1 text-[12px] text-rose-700 hover:bg-rose-50 disabled:opacity-50"
          >
            Decline and put it back
          </button>
          <button
            type="button"
            data-testid="proposal-reject-keep"
            disabled={busy}
            onClick={() => verdict("rejected")}
            className="rounded px-2 py-1 text-[11px] text-neutral-600 underline hover:bg-neutral-100 disabled:opacity-50"
          >
            mark rejected, leave it
          </button>
        </div>
      ) : null}
    </div>
  );
}

function MemberDiff({
  id, diff, before, after, workspaceSlug,
}: {
  id: string;
  diff: NodeDiff;
  before: Record<string, unknown> | null;
  after: Record<string, unknown>;
  workspaceSlug: string;
}) {
  const inline = changeCount(diff) <= INLINE_LIMIT;
  return (
    <section data-testid="proposal-member" data-node-id={id} className="rounded border border-neutral-200">
      <header className="flex items-baseline justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1">
        <span className="truncate text-[11px] font-medium text-neutral-700">
          {String(after.label ?? id)}
        </span>
        <span className="shrink-0 text-[10px] text-neutral-500">
          {before === null
            ? "added"
            : diff.unchanged
              ? "touched, nothing changed"
              : onlyGeometry(diff)
                ? "moved"
                : `${changeCount(diff)} change${changeCount(diff) === 1 ? "" : "s"}`}
        </span>
      </header>

      {before === null ? (
        <p className="px-2 py-2 text-[11px] text-neutral-500">
          New, so there is nothing to compare it against.
        </p>
      ) : diff.unchanged ? (
        <p className="px-2 py-2 text-[11px] text-neutral-500">
          This element is in the set but its captured fields are unchanged.
        </p>
      ) : (
        <div className="p-2">
          {diff.fields.map((f) => (
            <FieldRow key={f.field} field={f.field} before={f.before} after={f.after} inline={inline} />
          ))}
          {diff.rows.length > 0 ? (
            <RowDiffs rows={diff.rows} workspaceSlug={workspaceSlug} />
          ) : null}
        </div>
      )}
    </section>
  );
}

function FieldRow({
  field, before, after, inline,
}: {
  field: string;
  before: unknown;
  after: unknown;
  inline: boolean;
}) {
  const b = before === undefined || before === null || before === "" ? "—" : String(before);
  const a = after === undefined || after === null || after === "" ? "—" : String(after);
  return (
    <div data-testid="proposal-field" className="mb-1 text-[12px]">
      <div className="text-[10px] uppercase tracking-wide text-neutral-400">{field}</div>
      {inline ? (
        <p className="leading-snug">
          <span className="text-rose-700 line-through decoration-rose-300">{b}</span>{" "}
          <span className="text-emerald-800">{a}</span>
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <p className="rounded bg-rose-50 px-1.5 py-1 leading-snug text-rose-900">{b}</p>
          <p className="rounded bg-emerald-50 px-1.5 py-1 leading-snug text-emerald-900">{a}</p>
        </div>
      )}
    </div>
  );
}

function RowDiffs({ rows, workspaceSlug }: { rows: RowChange[]; workspaceSlug: string }) {
  return (
    <table className="w-full table-fixed text-[12px]">
      <tbody>
        {rows.map((r) => {
          const before = r.before ?? {};
          const after = r.after ?? {};
          const ref = (after.source_ref ?? before.source_ref) as ResolvableRef | undefined;
          return (
            <tr key={r.index} data-testid="proposal-row" data-kind={r.kind} className="border-b border-neutral-100 last:border-0">
              <td className="w-24 truncate py-1 pr-2 text-neutral-500">
                {String(after.key ?? before.key ?? `row ${r.index + 1}`)}
              </td>
              <td className="py-1">
                {r.kind === "added" ? (
                  <span className="text-emerald-800">{String(after.value ?? "")}</span>
                ) : r.kind === "removed" ? (
                  <span className="text-rose-700 line-through">{String(before.value ?? "")}</span>
                ) : (
                  <>
                    <span className="text-rose-700 line-through decoration-rose-300">
                      {String(before.value ?? "") || "—"}
                    </span>{" "}
                    <span className="text-emerald-800">{String(after.value ?? "") || "—"}</span>
                    {r.fields.includes("source_ref") ? (
                      <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] text-amber-900">
                        reference changed
                      </span>
                    ) : null}
                  </>
                )}
              </td>
              {/* The anchor survives into the diff. Reviewing a change to
                  grounded data means opening the source and checking it. */}
              <td className="w-8 text-right">
                {ref?.slug && ref?.page ? (
                  <SourceAnchorButton
                    workspaceSlug={workspaceSlug}
                    refValue={ref}
                    title={`Open page ${ref.page} in viewer`}
                    ariaLabel={`Open source page ${ref.page}`}
                    className="h-5 w-5"
                  />
                ) : null}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
