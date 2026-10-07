import { BACKEND_URL } from "@/api/client";

export type IntentsHandlers = {
  /** The server's `intent_pending {count}` signal: an immediate snapshot on
   *  connect, then a re-emit on every change to the pending set. Count only —
   *  the subscriber pulls the payload from `GET /api/intents[/all]`. */
  onPending?: (count: number) => void;
  onError?: (err: Event) => void;
};

/**
 * Subscribes to the project-level intents SSE stream
 * (`GET /api/intents/events`, issue #148). This is the push half of the
 * queue's push-notify / pull-payload design: the stream carries only a
 * pending-count signal, and the panel refetches the list when it fires.
 * Mirrors the reconnect shape of `CanvasSse` / `IngestsSse`.
 *
 * Note the signal only covers changes made through THIS server process; an
 * agent resolving over stdio MCP (a separate process) lands via the caller's
 * polling fallback instead.
 */
export class IntentsSse {
  private es: EventSource | null = null;
  private retryMs = 1000;
  private handlers: IntentsHandlers;

  constructor(handlers: IntentsHandlers) {
    this.handlers = handlers;
  }

  connect(): void {
    if (this.es) return;
    // jsdom / SSR safety: environments without EventSource fall back to the
    // caller's polling.
    if (typeof EventSource === "undefined") return;
    this.es = new EventSource(`${BACKEND_URL}/api/intents/events`);
    this.es.addEventListener("intent_pending", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as { count?: number };
        this.handlers.onPending?.(typeof data.count === "number" ? data.count : 0);
        this.retryMs = 1000;
      } catch (_err) {
        // ignore malformed payload
      }
    });
    this.es.onerror = (err) => {
      this.handlers.onError?.(err);
      this.disconnect();
      const next = Math.min(this.retryMs * 2, 30000);
      setTimeout(() => this.connect(), this.retryMs);
      this.retryMs = next;
    };
  }

  disconnect(): void {
    this.es?.close();
    this.es = null;
  }
}
