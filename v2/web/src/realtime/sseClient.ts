import { BACKEND_URL } from "@/api/client";

export type CanvasEvent = {
  id: string;
  type: string;
  workspace_id: string;
  version: number;
  payload: Record<string, unknown>;
  ts: number;
};

export type SseHandlers = {
  onSnapshot?: (state: unknown) => void;
  onPatch?: (event: CanvasEvent) => void;
  onError?: (err: Event) => void;
};

export class CanvasSse {
  private es: EventSource | null = null;
  private retryMs = 1000;
  private slug: string;
  private handlers: SseHandlers;

  constructor(slug: string, handlers: SseHandlers) {
    this.slug = slug;
    this.handlers = handlers;
  }

  connect(): void {
    if (this.es) return;
    this.es = new EventSource(`${BACKEND_URL}/api/workspaces/${this.slug}/events`);
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
