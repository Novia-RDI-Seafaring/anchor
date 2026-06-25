import { BACKEND_URL } from "@/api/client";

/** One in-flight (or just-resolved) ingest, as the activity surface sees it.
 *  Mirrors the server's `IngestActivity.to_dict()` (issue #51). */
export type IngestActivity = {
  slug: string;
  filename: string;
  stage: string;
  current: number;
  total: number;
  status: "running" | "done" | "failed";
  started_at: number;
  updated_at: number;
  pct: number | null;
  error?: string;
};

export type IngestsHandlers = {
  onIngests?: (ingests: IngestActivity[]) => void;
  onError?: (err: Event) => void;
};

/**
 * Subscribes to the project-level ingestion-activity SSE stream. The server
 * re-reads the durable activity records on a short cadence, so this sees every
 * ingest regardless of trigger (web drop, CLI `anchor ingest`, an MCP agent).
 * Mirrors the reconnect shape of `CanvasSse`.
 */
export class IngestsSse {
  private es: EventSource | null = null;
  private retryMs = 1000;
  private handlers: IngestsHandlers;

  constructor(handlers: IngestsHandlers) {
    this.handlers = handlers;
  }

  connect(): void {
    if (this.es) return;
    this.es = new EventSource(`${BACKEND_URL}/api/ingests/_stream/events`);
    this.es.addEventListener("ingests", (ev) => {
      try {
        this.handlers.onIngests?.(JSON.parse((ev as MessageEvent).data));
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
