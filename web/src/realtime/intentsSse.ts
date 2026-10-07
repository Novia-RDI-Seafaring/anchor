import { projectSse } from "./projectSse";

export type IntentsHandlers = {
  /** The server's `intent_pending {count}` signal: an immediate snapshot on
   *  connect, then a re-emit on every change to the pending set. Count only —
   *  the subscriber pulls the payload from `GET /api/intents[/all]`. */
  onPending?: (count: number) => void;
  onError?: (err: Event) => void;
};

/**
 * Subscribes to the project-level intents SSE stream
 * over the shared `GET /api/events` connection. This is the push half of the
 * queue's push-notify / pull-payload design: the stream carries only a
 * pending-count signal, and the panel refetches the list when it fires.
 * Reconnect and cleanup are owned by the shared transport.
 *
 * Note the signal only covers changes made through THIS server process; an
 * agent resolving over stdio MCP (a separate process) lands via the caller's
 * polling fallback instead.
 */
export class IntentsSse {
  private unsubscribe: (() => void) | null = null;
  private handlers: IntentsHandlers;

  constructor(handlers: IntentsHandlers) {
    this.handlers = handlers;
  }

  connect(): void {
    if (this.unsubscribe) return;
    this.unsubscribe = projectSse.subscribe({
      intent_pending: (payload) => {
        const data = payload as { count?: number };
        this.handlers.onPending?.(typeof data.count === "number" ? data.count : 0);
      },
      onError: this.handlers.onError,
    });
  }

  disconnect(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
  }
}
