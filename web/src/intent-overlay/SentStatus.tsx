import { useEffect, useState } from "react";
import { agentReach, UNHEARD_AFTER_S } from "./reach";
import type { Intent, OverlayHost } from "./ports";

/** Re-render every few seconds, so "just sent" turns into "nobody read it". */
function useNow(everyMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(timer);
  }, [everyMs]);
  return now;
}

/**
 * The line under a sent remark: who has seen it, or that nobody has.
 *
 * "Waiting for the agent" is only honest for a little while. Past
 * `UNHEARD_AFTER_S` with no inbox read, it says no agent has looked and
 * offers what to do about it.
 */
export function SentStatus({
  intent,
  hint,
  onWithdraw,
}: {
  intent: Intent | null | undefined;
  hint?: OverlayHost["display"]["listenHint"];
  onWithdraw: () => void;
}) {
  const now = useNow((UNHEARD_AFTER_S * 1000) / 3);
  const reach = agentReach(intent, now);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (!hint) return;
    try {
      await navigator.clipboard.writeText(hint.prompt);
      setCopied(true);
    } catch { /* Clipboard refused: the prompt is on screen to copy by hand. */ }
  };
  return (
    <div className="pointer-events-auto flex flex-col items-center gap-1" data-testid="comment-lasso-reach" data-reach={reach.kind}>
      <div className="flex items-center gap-1.5 text-[11px] text-neutral-400">
        <span>
          {reach.kind === "seen"
            ? `seen by ${reach.by} · ${reach.ago}`
            : reach.kind === "waiting"
              ? "sent · waiting for the agent"
              : "sent · no agent has read it yet"}
        </span>
        {reach.kind === "unheard" && hint ? (
          <button
            type="button"
            data-testid="comment-lasso-reach-how"
            className="rounded px-1 text-amber-700 underline-offset-2 hover:bg-amber-50 hover:underline"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "hide" : "how?"}
          </button>
        ) : null}
        <button
          type="button"
          data-testid="comment-lasso-withdraw"
          className="rounded px-1 text-neutral-500 underline-offset-2 hover:bg-neutral-100 hover:text-red-600 hover:underline"
          title="Take this remark back: the agent will not pick it up"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={onWithdraw}
        >
          withdraw
        </button>
      </div>
      {reach.kind === "unheard" && hint && open ? (
        <div
          data-testid="comment-lasso-reach-hint"
          className="w-64 rounded-md border border-amber-200 bg-white p-2 text-left text-[11px] text-neutral-700 shadow-md"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <div>Remarks wait in an inbox until an agent reads it. Ask yours to:</div>
          <div className="mt-1 rounded bg-neutral-50 px-1.5 py-1 font-mono text-[10px] text-neutral-800">{hint.prompt}</div>
          <div className="mt-1 flex items-center justify-between gap-2">
            <button
              type="button"
              data-testid="comment-lasso-reach-copy"
              className="rounded border border-neutral-300 px-1.5 py-0.5 text-[10px] hover:bg-neutral-100"
              onClick={() => void copy()}
            >
              {copied ? "copied" : "copy prompt"}
            </button>
            {hint.command ? (
              <span className="text-[10px] text-neutral-500">
                or run <code className="font-mono text-neutral-700">{hint.command}</code>
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
