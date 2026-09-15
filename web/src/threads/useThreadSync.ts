/**
 * useThreadSync — keeps the open thread's record live (#344).
 *
 * Fetches `GET /api/intents/{id}` when the panel opens a thread and again
 * whenever the shared intents feed ticks: that feed already listens to the
 * intents SSE `intent_pending` signal, polls every 8s, and reacts to this
 * window's own `anchor:intents-changed` nudge, so one subscription covers
 * all three legs. Canvas changes keep flowing through the canvas SSE
 * untouched; the ghost preview and staleness read the workspace store.
 */
import { useEffect } from "react";

import { intents } from "@/api/intents";
import { useIntentsFeed } from "@/shell/intentsFeed";

import { useThreadsStore } from "./threadsStore";

export function useThreadSync(threadId: string | null): void {
  const { tick } = useIntentsFeed();

  useEffect(() => {
    if (!threadId) return;
    let cancelled = false;
    const seqAtStart = useThreadsStore.getState().actionSeq;
    intents
      .get(threadId)
      .then((record) => {
        if (cancelled) return;
        const state = useThreadsStore.getState();
        // Ignore a late response for a thread the user has since closed.
        if (state.openThreadId !== threadId) return;
        // An action landed while this GET was in flight: its result is
        // newer than what the server saw when it served us, and the
        // action's own nudge has already scheduled a fresh refetch.
        if (state.actionSeq !== seqAtStart) return;
        state.setThread(record);
      })
      .catch((e) => {
        if (cancelled) return;
        if (useThreadsStore.getState().openThreadId !== threadId) return;
        useThreadsStore.getState().setThreadError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [threadId, tick]);
}
