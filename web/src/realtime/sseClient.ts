import { BACKEND_URL } from "@/api/client";

export type EventActor = {
  kind: "human" | "agent" | "system";
  id?: string | null;
  label?: string | null;
};

export type CanvasEvent = {
  id: string;
  type: string;
  workspace_id: string;
  version: number;
  payload: Record<string, unknown>;
  ts: number;
  // Who caused the event (#322). Absent/null on events recorded before
  // actor attribution existed.
  actor?: EventActor | null;
};

/**
 * One entry in a canvas's live presence roster. `via: "sse"` entries are
 * connected viewers (web UI, monitors); `via: "writes"` entries are agents
 * whose writes landed within the server's rolling window (~90s) — agents
 * don't hold SSE connections, their edits are their presence.
 */
export type PresenceEntry = {
  client_id?: string;
  id?: string | null;
  kind: "human" | "agent" | "system";
  label?: string | null;
  connected_at: number;
  last_write_at?: number;
  via: "sse" | "writes";
};

/**
 * A `presence` SSE event: the FULL current roster (clients stay stateless —
 * each event replaces what they knew). `you` names this connection's own
 * entry and is only present on the initial roster sent right after the
 * snapshot.
 */
export type PresencePayload = {
  workspace: string;
  present: PresenceEntry[];
  you?: string;
};

export type SseHandlers = {
  onSnapshot?: (state: unknown) => void;
  onPatch?: (event: CanvasEvent) => void;
  onPresence?: (payload: PresencePayload) => void;
  onError?: (err: Event) => void;
};

export type SseOptions = {
  /** How this viewer appears in the presence roster (default: human/"browser"). */
  actorKind?: "human" | "agent" | "system";
  actorLabel?: string;
};

export class CanvasSse {
  private es: EventSource | null = null;
  private retryMs = 1000;
  private slug: string;
  private handlers: SseHandlers;
  private options: SseOptions;

  constructor(slug: string, handlers: SseHandlers, options: SseOptions = {}) {
    this.slug = slug;
    this.handlers = handlers;
    this.options = options;
  }

  private url(): string {
    const params = new URLSearchParams();
    if (this.options.actorKind) params.set("actor_kind", this.options.actorKind);
    if (this.options.actorLabel) params.set("actor_label", this.options.actorLabel);
    const query = params.toString();
    return `${BACKEND_URL}/api/workspaces/${this.slug}/events${query ? `?${query}` : ""}`;
  }

  connect(): void {
    if (this.es) return;
    this.es = new EventSource(this.url());
    this.es.addEventListener("snapshot", (ev) => {
      try {
        this.handlers.onSnapshot?.(JSON.parse((ev as MessageEvent).data));
        this.retryMs = 1000;
      } catch (_err) {
        // ignore malformed snapshot
      }
    });
    this.es.addEventListener("patch", (ev) => {
      try {
        this.handlers.onPatch?.(JSON.parse((ev as MessageEvent).data));
      } catch (_err) {
        // ignore malformed patch
      }
    });
    this.es.addEventListener("presence", (ev) => {
      try {
        this.handlers.onPresence?.(JSON.parse((ev as MessageEvent).data));
      } catch (_err) {
        // ignore malformed presence
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
