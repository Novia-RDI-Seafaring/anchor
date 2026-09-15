/**
 * ThreadPanel — the docked review surface for a scoped-ask thread (#344).
 *
 * Opened by a pin on the canvas, the Intents tab, or a fresh ask. Shows the
 * thread's items in order: messages plain; open questions with an inline
 * answer box; suggestions with rationale, op count and state chip (click →
 * ghost preview on the canvas; Approve / Decline / Comment); results with
 * the summary and "show what changed" (the catch-up diff since the ask's
 * `base_version`). A composer at the bottom adds a human message item.
 *
 * Data: `useThreadSync` keeps the record live off the shared intents feed
 * (SSE signal + poll + local nudge). Actions go through the intents API
 * and put the returned record straight into the store, so the panel
 * reflects an approve / decline / answer before the feed catches up. A
 * pending suggestion whose ops reference elements that are gone renders as
 * stale, with Approve disabled — the server would refuse it anyway.
 *
 * Shell rule: this layer talks HTTP only; it never touches canvas/ internals.
 * Visual language matches the shell panels (Intents / References / Catch-up).
 */
import { useReactFlow } from "@xyflow/react";
import { useState } from "react";

import { canvases, type CanvasChanges } from "@/api/canvases";
import { intents, type Intent, type ThreadItem } from "@/api/intents";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import {
  authorName,
  boundingBox,
  isStaleSuggestion,
  opCount,
  orderedItems,
  targetsOnCanvas,
  threadTitle,
} from "@/threads/threads";
import { useThreadsStore } from "@/threads/threadsStore";
import { useThreadSync } from "@/threads/useThreadSync";

import { ChangeGroups } from "./CatchUpPanel";
import { timeAgo } from "./intentsFeed";

type Props = { workspaceSlug: string };

export function ThreadPanel({ workspaceSlug }: Props) {
  const openThreadId = useThreadsStore((s) => s.openThreadId);
  if (!openThreadId) return null;
  return <ThreadPanelBody key={openThreadId} threadId={openThreadId} workspaceSlug={workspaceSlug} />;
}

export function ThreadPanelBody({
  threadId,
  workspaceSlug,
}: {
  threadId: string;
  workspaceSlug: string;
}) {
  useThreadSync(threadId);
  const thread = useThreadsStore((s) => s.thread);
  const threadError = useThreadsStore((s) => s.threadError);
  const closeThread = useThreadsStore((s) => s.closeThread);
  const applyActionResult = useThreadsStore((s) => s.applyActionResult);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = async (fn: () => Promise<Intent>) => {
    try {
      const record = await fn();
      applyActionResult(record);
      setActionError(null);
    } catch (e) {
      setActionError(String(e));
    }
  };

  const items = orderedItems(thread);
  const isOpen = thread?.status === "pending";

  return (
    <div
      className="absolute bottom-3 right-3 top-3 z-30 flex w-80 flex-col overflow-hidden rounded-md border border-neutral-200 bg-white shadow-lg"
      data-testid="thread-panel"
      data-thread-id={threadId}
    >
      <div className="flex items-baseline justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          Thread
          {thread ? (
            <span
              className={cn(
                "ml-1.5 rounded-full px-1.5 py-px text-[9px] normal-case tracking-normal",
                isOpen ? "bg-amber-100 text-amber-700" : "bg-green-100 text-green-700",
              )}
              data-testid="thread-status"
            >
              {isOpen ? "open" : "resolved"}
            </span>
          ) : null}
        </span>
        <button
          type="button"
          onClick={closeThread}
          className="rounded px-1 text-[10px] text-neutral-400 hover:bg-neutral-200 hover:text-neutral-700"
          title="Close thread"
          aria-label="Close thread panel"
          data-testid="thread-close"
        >
          ✕
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-1.5">
        {threadError ? (
          <div className="px-2 text-[10px] text-red-600" data-testid="thread-error">
            error: {threadError}
          </div>
        ) : null}
        {!thread ? (
          <div className="px-2 py-2 text-[10px] italic text-neutral-400">loading thread…</div>
        ) : (
          <>
            <ThreadHeader thread={thread} workspaceSlug={workspaceSlug} />
            {items.length === 0 ? (
              <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
                no replies yet — the agent answers here
              </div>
            ) : (
              items.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  thread={thread}
                  workspaceSlug={workspaceSlug}
                  run={run}
                />
              ))
            )}
          </>
        )}
        {actionError ? (
          <div className="px-2 text-[10px] text-red-600" data-testid="thread-action-error">
            error: {actionError}
          </div>
        ) : null}
      </div>

      {thread ? (
        <MessageComposer
          placeholder="Comment in this thread… (Enter to send)"
          testId="thread-composer"
          onSubmit={(text) => run(() => intents.addItem(thread.id, { type: "message", text }))}
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header: the ask, its targets, base version.
// ---------------------------------------------------------------------------

function ThreadHeader({ thread, workspaceSlug }: { thread: Intent; workspaceSlug: string }) {
  const nodes = useCanvasStore((s) => s.nodes);
  const { setCenter, getZoom } = useReactFlow();
  const targetIds = targetsOnCanvas(thread, workspaceSlug);
  const present = targetIds.filter((id) => nodes[id]);
  const total = thread.targets?.length ?? 0;

  const focusTargets = () => {
    const box = boundingBox(present, nodes);
    if (!box) return;
    void setCenter(box.x + box.width / 2, box.y + box.height / 2, {
      zoom: getZoom(),
      duration: 400,
    });
  };

  return (
    <div className="rounded border border-amber-200 bg-amber-50/50 px-2 py-1.5" data-testid="thread-ask">
      <div className="break-words text-xs font-medium text-neutral-800">{threadTitle(thread)}</div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[10px] text-neutral-500">
        <button
          type="button"
          onClick={focusTargets}
          disabled={present.length === 0}
          className={cn(
            "rounded px-1 -mx-1",
            present.length > 0 ? "hover:bg-amber-100" : "cursor-default",
          )}
          title={present.length > 0 ? "Center the targeted elements" : "Targets are no longer on this canvas"}
          data-testid="thread-targets"
        >
          {total} {total === 1 ? "target" : "targets"}
          {present.length < targetIds.length ? ` (${targetIds.length - present.length} gone)` : ""}
        </button>
        {typeof thread.base_version === "number" ? <span>· v{thread.base_version}</span> : null}
        <span>· {timeAgo(thread.created_at)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Items
// ---------------------------------------------------------------------------

type RunFn = (fn: () => Promise<Intent>) => Promise<void>;

function ItemRow({
  item,
  thread,
  workspaceSlug,
  run,
}: {
  item: ThreadItem;
  thread: Intent;
  workspaceSlug: string;
  run: RunFn;
}) {
  switch (item.type) {
    case "question":
      return <QuestionItem item={item} thread={thread} run={run} />;
    case "suggestion":
      return <SuggestionItem item={item} thread={thread} run={run} />;
    case "result":
      return <ResultItem item={item} thread={thread} workspaceSlug={workspaceSlug} />;
    default:
      return <MessageItem item={item} />;
  }
}

function ItemMeta({ item, extra }: { item: ThreadItem; extra?: React.ReactNode }) {
  return (
    <div className="mb-0.5 flex items-center gap-1 text-[10px] text-neutral-500">
      <span
        className={cn(
          "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
          item.author?.kind === "human" ? "bg-sky-500" : item.author?.kind === "system" ? "bg-neutral-400" : "bg-violet-500",
        )}
        aria-hidden="true"
      />
      <span className="font-medium text-neutral-600">{authorName(item.author)}</span>
      <span>· {timeAgo(item.created_at)}</span>
      {extra}
    </div>
  );
}

function MessageItem({ item }: { item: ThreadItem }) {
  return (
    <div
      className="rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs"
      data-testid="thread-item"
      data-item-type={item.type}
      data-item-id={item.id}
    >
      <ItemMeta item={item} />
      <div className="whitespace-pre-wrap break-words text-neutral-800">{item.text}</div>
    </div>
  );
}

function QuestionItem({ item, thread, run }: { item: ThreadItem; thread: Intent; run: RunFn }) {
  const open = item.state === "open";
  return (
    <div
      className="rounded border border-sky-200 bg-sky-50/40 px-2 py-1.5 text-xs"
      data-testid="thread-item"
      data-item-type="question"
      data-item-id={item.id}
      data-state={item.state ?? ""}
    >
      <ItemMeta
        item={item}
        extra={<span className="rounded-full bg-sky-100 px-1.5 text-[9px] text-sky-700">question</span>}
      />
      <div className="whitespace-pre-wrap break-words text-neutral-800">{item.text}</div>
      {open ? (
        <MessageComposer
          placeholder="Answer… (Enter to send)"
          testId="thread-answer"
          compact
          onSubmit={(text) => run(() => intents.answer(thread.id, item.id, text))}
        />
      ) : item.answer ? (
        <div className="mt-1 border-l-2 border-sky-300 pl-2 text-[11px] text-neutral-700" data-testid="thread-answer-text">
          {item.answer}
        </div>
      ) : null}
    </div>
  );
}

const SUGGESTION_CHIP: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  applied: "bg-green-100 text-green-700",
  declined: "bg-rose-100 text-rose-700",
  superseded: "bg-neutral-200 text-neutral-600",
};

function SuggestionItem({ item, thread, run }: { item: ThreadItem; thread: Intent; run: RunFn }) {
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const previewItemId = useThreadsStore((s) => s.previewItemId);
  const togglePreview = useThreadsStore((s) => s.togglePreview);
  const [mode, setMode] = useState<null | "decline" | "comment">(null);
  const [busy, setBusy] = useState(false);

  const state = item.state ?? "pending";
  const pending = state === "pending";
  const stale = isStaleSuggestion(item, nodes, edges);
  const previewing = previewItemId === item.id;
  const count = opCount(item);

  const act = async (fn: () => Promise<Intent>) => {
    setBusy(true);
    try {
      await run(fn);
      setMode(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={cn(
        "rounded border px-2 py-1.5 text-xs transition",
        previewing ? "border-violet-400 ring-1 ring-violet-300" : "border-violet-200",
        pending ? "bg-violet-50/40" : "bg-white",
        state === "superseded" || state === "declined" ? "opacity-70" : "",
      )}
      data-testid="thread-item"
      data-item-type="suggestion"
      data-item-id={item.id}
      data-state={state}
      data-stale={stale ? "true" : "false"}
      data-previewing={previewing ? "true" : "false"}
    >
      <button
        type="button"
        onClick={() => togglePreview(item.id)}
        className="block w-full text-left"
        title={previewing ? "Hide the preview" : "Preview these changes on the canvas"}
        aria-pressed={previewing}
        data-testid="thread-suggestion-toggle"
      >
        <ItemMeta
          item={item}
          extra={
            <>
              <span
                className={cn("rounded-full px-1.5 text-[9px]", SUGGESTION_CHIP[state] ?? SUGGESTION_CHIP.pending)}
                data-testid="thread-suggestion-state"
              >
                {state}
              </span>
              <span className="text-neutral-400">
                · {count} {count === 1 ? "op" : "ops"}
              </span>
              {item.supersedes ? <span className="text-neutral-400">· revision</span> : null}
            </>
          }
        />
        <div className="whitespace-pre-wrap break-words text-neutral-800">{item.text}</div>
        {stale ? (
          <div className="mt-1 text-[10px] italic text-rose-600" data-testid="thread-suggestion-stale">
            stale — references elements no longer on the canvas
          </div>
        ) : null}
        {state === "applied" && item.applied_versions?.length ? (
          <div className="mt-1 text-[10px] text-neutral-400">
            applied as v{item.applied_versions.join(", v")}
          </div>
        ) : null}
        <div className="mt-0.5 text-[9px] italic text-neutral-400">
          {previewing ? "previewing on canvas" : "click to preview on canvas"}
        </div>
      </button>

      {pending ? (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <ActionButton
            tone="emerald"
            disabled={busy || stale}
            title={stale ? "Cannot apply: the canvas changed under this suggestion" : "Apply these changes"}
            testId="thread-approve"
            onClick={() => void act(() => intents.apply(thread.id, item.id))}
          >
            Approve
          </ActionButton>
          <ActionButton
            tone="rose"
            disabled={busy}
            testId="thread-decline"
            onClick={() => setMode((m) => (m === "decline" ? null : "decline"))}
          >
            Decline
          </ActionButton>
          <ActionButton
            tone="neutral"
            disabled={busy}
            testId="thread-comment"
            onClick={() => setMode((m) => (m === "comment" ? null : "comment"))}
          >
            Comment
          </ActionButton>
        </div>
      ) : null}

      {mode === "decline" ? (
        <MessageComposer
          placeholder="Why? (optional, Enter to decline)"
          testId="thread-decline-comment"
          submitLabel="Decline"
          allowEmpty
          compact
          onSubmit={(text) => act(() => intents.decline(thread.id, item.id, text || undefined))}
        />
      ) : null}
      {mode === "comment" ? (
        <MessageComposer
          placeholder="Comment on this suggestion… (Enter to send)"
          testId="thread-suggestion-comment"
          compact
          onSubmit={(text) => act(() => intents.addItem(thread.id, { type: "message", text }))}
        />
      ) : null}
    </div>
  );
}

function ResultItem({
  item,
  thread,
  workspaceSlug,
}: {
  item: ThreadItem;
  thread: Intent;
  workspaceSlug: string;
}) {
  const [changes, setChanges] = useState<CanvasChanges | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canDiff = typeof thread.base_version === "number";

  const showChanges = async () => {
    if (!canDiff || busy) return;
    if (changes) {
      setChanges(null);
      return;
    }
    setBusy(true);
    try {
      setChanges(await canvases.changes(workspaceSlug, thread.base_version as number));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="rounded border border-green-200 bg-green-50/40 px-2 py-1.5 text-xs"
      data-testid="thread-item"
      data-item-type="result"
      data-item-id={item.id}
    >
      <ItemMeta
        item={item}
        extra={<span className="rounded-full bg-green-100 px-1.5 text-[9px] text-green-700">result</span>}
      />
      <div className="whitespace-pre-wrap break-words text-neutral-800">{item.text}</div>
      {canDiff ? (
        <button
          type="button"
          onClick={() => void showChanges()}
          disabled={busy}
          className="mt-1 rounded border border-neutral-300 bg-white px-2 py-0.5 text-[10px] text-neutral-700 hover:bg-neutral-100 disabled:opacity-40"
          data-testid="thread-show-changes"
          aria-expanded={changes !== null}
        >
          {changes ? "Hide what changed" : `Show what changed since v${thread.base_version}`}
        </button>
      ) : null}
      {error ? <div className="mt-1 text-[10px] text-red-600">error: {error}</div> : null}
      {changes ? (
        <div className="mt-1 space-y-1" data-testid="thread-changes">
          <div className="px-1 text-[9px] italic text-neutral-400">
            v{changes.from_version} → v{changes.to_version}
          </div>
          {changes.groups.length === 0 ? (
            <div className="px-1 text-[10px] italic text-neutral-400">nothing changed</div>
          ) : (
            <ChangeGroups groups={changes.groups} />
          )}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small primitives
// ---------------------------------------------------------------------------

function ActionButton({
  children,
  tone,
  disabled,
  title,
  testId,
  onClick,
}: {
  children: React.ReactNode;
  tone: "emerald" | "rose" | "neutral";
  disabled?: boolean;
  title?: string;
  testId: string;
  onClick: () => void;
}) {
  const tones = {
    emerald: "border-emerald-300 text-emerald-700 hover:bg-emerald-50",
    rose: "border-rose-300 text-rose-700 hover:bg-rose-50",
    neutral: "border-neutral-300 text-neutral-700 hover:bg-neutral-100",
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      data-testid={testId}
      className={cn(
        "rounded border bg-white px-2 py-0.5 text-[10px] font-medium disabled:cursor-default disabled:opacity-40",
        tones[tone],
      )}
    >
      {children}
    </button>
  );
}

function MessageComposer({
  placeholder,
  testId,
  onSubmit,
  submitLabel = "Send",
  allowEmpty = false,
  compact = false,
}: {
  placeholder: string;
  testId: string;
  onSubmit: (text: string) => Promise<void>;
  submitLabel?: string;
  allowEmpty?: boolean;
  compact?: boolean;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const trimmed = text.trim();
    if ((!trimmed && !allowEmpty) || busy) return;
    setBusy(true);
    try {
      await onSubmit(trimmed);
      setText("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={cn(
        "flex items-end gap-1",
        compact ? "mt-1.5" : "border-t border-neutral-200 bg-neutral-50/60 p-1.5",
      )}
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void submit();
          }
        }}
        rows={compact ? 1 : 2}
        placeholder={placeholder}
        aria-label={placeholder}
        data-testid={`${testId}-input`}
        className="min-w-0 flex-1 resize-none rounded border border-neutral-300 bg-white px-1.5 py-1 text-xs placeholder:italic placeholder:text-neutral-400"
      />
      <button
        type="button"
        onClick={() => void submit()}
        disabled={(!text.trim() && !allowEmpty) || busy}
        data-testid={`${testId}-submit`}
        className="shrink-0 rounded border border-neutral-300 bg-white px-2 py-0.5 text-[10px] font-medium text-neutral-700 hover:bg-neutral-100 disabled:cursor-default disabled:opacity-40"
      >
        {submitLabel}
      </button>
    </div>
  );
}
