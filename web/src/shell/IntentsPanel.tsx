/**
 * IntentsPanel — the delegation queue made visible (#323, part 2 of #321).
 *
 * A FilesExplorer tab that surfaces the project-level intents queue (#148):
 * open intents at the top in agent-drain order, a collapsed "recently
 * resolved" section below, and a create form that enqueues a free-text
 * `user_request` — offering the currently selected canvas node as the
 * target. Dismissing an open intent resolves it with `{dismissed: true}`.
 *
 * Data comes in through props from `useIntentsFeed` (mounted by
 * FilesExplorer so the tab badge shares the same feed); mutations go out
 * through the intents API, whose `anchor:intents-changed` nudge makes the
 * feed refetch. Visual language matches the shell panels: small uppercase
 * section headers, bordered rows, neutral palette, dense type.
 */
import { useState } from "react";

import { intents, type Intent } from "@/api/intents";
import { cn } from "@/lib/cn";
import { useCanvasStore } from "@/stores/canvasStore";
import { useUiStore } from "@/stores/uiStore";

import {
  intentTitle,
  kindLabel,
  resolutionText,
  targetNodeId,
  timeAgo,
} from "./intentsFeed";

type Props = {
  workspaceSlug: string;
  open: Intent[];
  resolved: Intent[];
  error: string | null;
};

export function IntentsPanel({ workspaceSlug, open, resolved, error }: Props) {
  const [showResolved, setShowResolved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const onDismiss = async (intent: Intent) => {
    try {
      await intents.resolve(intent.id, { dismissed: true });
      setActionError(null);
    } catch (e) {
      setActionError(String(e));
    }
  };

  return (
    <div
      className="flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden bg-white"
      data-testid="intents-panel"
    >
      <div className="flex items-baseline justify-between border-b border-neutral-200 bg-neutral-50 px-2 py-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">
          Intents ({open.length} open)
        </span>
        <span className="text-[9px] italic text-neutral-400">the agent&apos;s inbox</span>
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-1.5">
        <CreateIntentForm workspaceSlug={workspaceSlug} onError={setActionError} />

        {error ? (
          <div className="px-2 text-[10px] text-red-600">error: {error}</div>
        ) : null}
        {actionError ? (
          <div className="px-2 text-[10px] text-red-600" data-testid="intents-action-error">
            error: {actionError}
          </div>
        ) : null}

        <div className="space-y-1">
          {open.length === 0 ? (
            <Hint text="no open intents — queue a request above, or drop a document on the canvas" />
          ) : (
            open.map((intent) => (
              <IntentRow key={intent.id} intent={intent} onDismiss={() => onDismiss(intent)} />
            ))
          )}
        </div>

        {resolved.length > 0 ? (
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => setShowResolved((v) => !v)}
              aria-expanded={showResolved}
              data-testid="intents-resolved-toggle"
              className="flex w-full items-center gap-1 px-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-500 hover:text-neutral-700"
            >
              <span
                className={cn(
                  "inline-block transition-transform",
                  showResolved ? "rotate-90" : "rotate-0",
                )}
                aria-hidden="true"
              >
                ▸
              </span>
              Recently resolved ({resolved.length})
            </button>
            {showResolved
              ? resolved.map((intent) => <IntentRow key={intent.id} intent={intent} />)
              : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Hint({ text }: { text: string }) {
  return (
    <div className="rounded border border-dashed border-neutral-300 px-2 py-2 text-[10px] italic text-neutral-500">
      {text}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CreateIntentForm — free-text request + optional selected-node target.
// ---------------------------------------------------------------------------

function CreateIntentForm({
  workspaceSlug,
  onError,
}: {
  workspaceSlug: string;
  onError: (err: string | null) => void;
}) {
  const [text, setText] = useState("");
  const [attachNode, setAttachNode] = useState(true);
  const [busy, setBusy] = useState(false);

  const selectedNodeId = useUiStore((s) => s.selectedNodeId);
  const selectedNode = useCanvasStore((s) =>
    selectedNodeId ? s.nodes[selectedNodeId] ?? null : null,
  );

  const submit = async () => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await intents.create({
        text: trimmed,
        workspaceSlug,
        nodeId: attachNode && selectedNode ? selectedNode.id : null,
      });
      setText("");
      onError(null);
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-1 rounded border border-neutral-200 bg-neutral-50/60 p-1.5">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void submit();
          }
        }}
        rows={2}
        placeholder="Ask the agent… (Enter to queue)"
        aria-label="New intent text"
        data-testid="intent-text-input"
        className="w-full resize-none rounded border border-neutral-300 bg-white px-1.5 py-1 text-xs placeholder:italic placeholder:text-neutral-400"
      />
      <div className="flex items-center justify-between gap-2">
        {selectedNode ? (
          <label className="flex min-w-0 items-center gap-1 text-[10px] text-neutral-600">
            <input
              type="checkbox"
              checked={attachNode}
              onChange={(e) => setAttachNode(e.target.checked)}
              data-testid="intent-attach-node"
              className="h-3 w-3"
            />
            <span className="truncate">
              target: {selectedNode.label || selectedNode.id}
            </span>
          </label>
        ) : (
          <span className="text-[9px] italic text-neutral-400">
            select a node to target it
          </span>
        )}
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!text.trim() || busy}
          data-testid="intent-submit"
          className="shrink-0 rounded border border-neutral-300 bg-white px-2 py-0.5 text-[10px] font-medium text-neutral-700 hover:bg-neutral-100 disabled:cursor-default disabled:opacity-40"
        >
          Queue intent
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// IntentRow — one queue entry. Open rows show a pulsing pending dot + dismiss;
// resolved rows show the resolution text when the record carries one.
// ---------------------------------------------------------------------------

function IntentRow({
  intent,
  onDismiss,
}: {
  intent: Intent;
  onDismiss?: () => void;
}) {
  const isOpen = intent.status === "pending";
  const nodeId = targetNodeId(intent);
  const resolution = isOpen ? null : resolutionText(intent);
  const when = isOpen
    ? timeAgo(intent.created_at)
    : timeAgo(intent.resolved_at ?? intent.created_at);

  return (
    <div
      className={cn(
        "group rounded border px-2 py-1.5 text-xs",
        isOpen
          ? "border-amber-200 bg-amber-50/50"
          : "border-neutral-200 bg-white",
      )}
      data-testid="intent-row"
      data-intent-id={intent.id}
      data-status={intent.status}
    >
      <div className="flex items-start gap-1.5">
        <span
          className={cn(
            "mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full",
            isOpen ? "animate-pulse bg-amber-500" : "bg-green-500",
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
            {intentTitle(intent)}
          </div>
          <div className="mt-0.5 truncate text-[10px] text-neutral-500">
            {kindLabel(intent.kind)}
            {intent.origin_canvas_id ? ` · ${intent.origin_canvas_id}` : ""}
            {nodeId ? ` · node ${nodeId}` : ""}
            {when ? ` · ${when}` : ""}
          </div>
          {resolution ? (
            <div
              className="mt-0.5 break-words text-[10px] italic text-neutral-400"
              data-testid="intent-resolution"
            >
              {resolution}
            </div>
          ) : null}
        </div>
        {isOpen && onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            className="shrink-0 rounded px-1 text-[10px] text-neutral-400 opacity-0 transition-opacity hover:bg-red-100 hover:text-red-600 group-hover:opacity-100"
            title="Dismiss (resolve without acting)"
            aria-label="Dismiss intent"
            data-testid="intent-dismiss"
          >
            ✕
          </button>
        ) : null}
      </div>
    </div>
  );
}
