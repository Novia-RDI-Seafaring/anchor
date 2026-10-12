import { projectSse } from "./projectSse";

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
  private unsubscribe: (() => void) | null = null;
  private slug: string;
  private handlers: SseHandlers;
  private options: SseOptions;

  constructor(slug: string, handlers: SseHandlers, options: SseOptions = {}) {
    this.slug = slug;
    this.handlers = handlers;
    this.options = options;
  }

  connect(): void {
    if (this.unsubscribe) return;
    this.unsubscribe = projectSse.subscribe({
      snapshot: this.handlers.onSnapshot,
      patch: (payload) => this.handlers.onPatch?.(payload as CanvasEvent),
      presence: (payload) => this.handlers.onPresence?.(payload as PresencePayload),
      onError: this.handlers.onError,
    }, { slug: this.slug, ...this.options });
  }

  disconnect(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
  }
}
