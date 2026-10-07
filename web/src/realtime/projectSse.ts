import { BACKEND_URL } from "@/api/client";

type EventName = "snapshot" | "patch" | "presence" | "intent_pending" | "ingests";
type Handlers = Partial<Record<EventName, (payload: unknown) => void>> & {
  onError?: (error: Event) => void;
};
type Workspace = { slug: string; actorKind?: string; actorLabel?: string };
type Subscriber = { handlers: Handlers; workspace?: Workspace };
const EVENT_NAMES: EventName[] = ["snapshot", "patch", "presence", "intent_pending", "ingests"];

/** One browser connection, shared by the canvas and project panels in this tab. */
class ProjectSse {
  private subscribers = new Set<Subscriber>();
  private source: EventSource | null = null;
  private currentUrl: string | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private retryMs = 1000;
  private latest = new Map<EventName, unknown>();

  subscribe(handlers: Handlers, workspace?: Workspace): () => void {
    const subscriber = { handlers, workspace };
    this.subscribers.add(subscriber);
    this.reconcile();
    // Panels can mount after the stream's initial snapshots have arrived.
    for (const [name, payload] of this.latest) this.deliver(subscriber, name, payload);
    return () => {
      this.subscribers.delete(subscriber);
      this.reconcile();
    };
  }

  private url(): string {
    const workspace = [...this.subscribers].find((s) => s.workspace)?.workspace;
    const params = new URLSearchParams();
    if (workspace) {
      params.set("canvas", workspace.slug);
      if (workspace.actorKind) params.set("actor_kind", workspace.actorKind);
      if (workspace.actorLabel) params.set("actor_label", workspace.actorLabel);
    }
    const query = params.toString();
    return `${BACKEND_URL}/api/events${query ? `?${query}` : ""}`;
  }

  private reconcile(): void {
    const url = this.subscribers.size ? this.url() : null;
    if (url !== this.currentUrl) {
      this.close();
      this.currentUrl = url;
      this.latest.delete("presence");
      this.retryMs = 1000;
    }
    if (!url) {
      this.latest.clear();
      return;
    }
    if (!this.source && this.retryTimer === null) this.connect();
  }

  private deliver(subscriber: Subscriber, name: EventName, payload: unknown): void {
    if (name === "snapshot" || name === "patch" || name === "presence") {
      const workspace = [...this.subscribers].find((s) => s.workspace)?.workspace;
      if (!subscriber.workspace || subscriber.workspace.slug !== workspace?.slug) return;
    }
    try {
      subscriber.handlers[name]?.(payload);
    } catch (_err) {
      // A failing panel must not prevent other consumers from receiving updates.
    }
  }

  private connect(): void {
    if (this.source || !this.currentUrl || typeof EventSource === "undefined") return;
    const source = new EventSource(this.currentUrl);
    this.source = source;
    for (const name of EVENT_NAMES) {
      source.addEventListener(name, (event) => {
        if (this.source !== source) return;
        let payload: unknown;
        try {
          payload = JSON.parse((event as MessageEvent).data);
        } catch (_err) {
          return;
        }
        this.retryMs = 1000;
        // Cached canvas snapshots become stale after patches. Only project
        // snapshots and the full presence roster are safe to replay.
        if (name !== "patch" && name !== "snapshot") this.latest.set(name, payload);
        for (const subscriber of this.subscribers) this.deliver(subscriber, name, payload);
      });
    }
    source.onerror = (error) => {
      if (this.source !== source) return;
      this.close();
      for (const subscriber of this.subscribers) {
        try {
          subscriber.handlers.onError?.(error);
        } catch (_err) {
          // Keep reconnecting even if one consumer's error handler fails.
        }
      }
      if (!this.subscribers.size) return;
      this.retryTimer = setTimeout(() => {
        this.retryTimer = null;
        this.connect();
      }, this.retryMs);
      this.retryMs = Math.min(this.retryMs * 2, 30000);
    };
  }

  private close(): void {
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.source?.close();
    this.source = null;
  }
}

export const projectSse = new ProjectSse();
