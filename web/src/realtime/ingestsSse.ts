import { projectSse } from "./projectSse";

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
 * Shares one connection and reconnect loop with the canvas and intents panel.
 */
export class IngestsSse {
  private unsubscribe: (() => void) | null = null;
  private handlers: IngestsHandlers;

  constructor(handlers: IngestsHandlers) {
    this.handlers = handlers;
  }

  connect(): void {
    if (this.unsubscribe) return;
    this.unsubscribe = projectSse.subscribe({
      ingests: (payload) => this.handlers.onIngests?.(payload as IngestActivity[]),
      onError: this.handlers.onError,
    });
  }

  disconnect(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
  }
}
