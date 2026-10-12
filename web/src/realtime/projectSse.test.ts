import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IngestsSse } from "./ingestsSse";
import { IntentsSse } from "./intentsSse";
import { CanvasSse } from "./sseClient";

let connectionLimit = 1;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onerror: ((error: Event) => void) | null = null;
  closed = false;
  private listeners: Record<string, ((event: MessageEvent) => void)[]> = {};

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
    // Pin the HTTP/1 pool regression throughout mount and navigation, not just
    // after all consumers have settled.
    expect(FakeEventSource.instances.filter((s) => !s.closed).length).toBeLessThanOrEqual(connectionLimit);
  }

  addEventListener(name: string, listener: (event: MessageEvent) => void) {
    (this.listeners[name] ??= []).push(listener);
  }

  emit(name: string, payload: unknown) {
    for (const listener of this.listeners[name] ?? []) {
      listener({ data: JSON.stringify(payload) } as MessageEvent);
    }
  }

  close() {
    this.closed = true;
  }
}

const clients: { connect(): void; disconnect(): void }[] = [];
const start = <T extends { connect(): void; disconnect(): void }>(client: T): T => {
  clients.push(client);
  client.connect();
  return client;
};
const active = () => FakeEventSource.instances.filter((s) => !s.closed);

beforeEach(() => {
  vi.useFakeTimers();
  FakeEventSource.instances = [];
  connectionLimit = 1;
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  for (const client of clients.splice(0)) client.disconnect();
  expect(active()).toHaveLength(0);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("per-tab multiplexed SSE", () => {
  it("fans all named events to the existing consumers over one connection", () => {
    const onSnapshot = vi.fn();
    const onPatch = vi.fn();
    const onPresence = vi.fn();
    const onPending = vi.fn();
    const onIngests = vi.fn();
    start(new CanvasSse("alpha", { onSnapshot, onPatch, onPresence }));
    start(new IntentsSse({ onPending }));
    start(new IngestsSse({ onIngests }));
    expect(FakeEventSource.instances).toHaveLength(1);
    const [source] = active();
    source!.emit("snapshot", { version: 3 });
    source!.emit("patch", { type: "NodeAdded", version: 4 });
    source!.emit("presence", { workspace: "alpha", present: [] });
    source!.emit("intent_pending", { count: 2 });
    source!.emit("ingests", [{ slug: "pump", status: "running" }]);
    expect(onSnapshot).toHaveBeenCalledWith({ version: 3 });
    expect(onPatch).toHaveBeenCalledWith({ type: "NodeAdded", version: 4 });
    expect(onPresence).toHaveBeenCalledWith({ workspace: "alpha", present: [] });
    expect(onPending).toHaveBeenCalledWith(2);
    expect(onIngests).toHaveBeenCalledWith([{ slug: "pump", status: "running" }]);
  });

  it("adds and switches canvases while project panels remain subscribed", () => {
    start(new IntentsSse({}));
    start(new IngestsSse({}));
    const first = start(new CanvasSse("alpha", {}));
    expect(new URL(active()[0]!.url, "http://localhost").searchParams.get("canvas")).toBe("alpha");
    first.disconnect();
    start(new CanvasSse("beta", {}, { actorKind: "human", actorLabel: "monitor" }));
    const url = new URL(active()[0]!.url, "http://localhost");
    expect(url.searchParams.get("canvas")).toBe("beta");
    expect(url.searchParams.get("actor_kind")).toBe("human");
    expect(url.searchParams.get("actor_label")).toBe("monitor");
  });

  it("replays project snapshots to late panels and keeps remaining consumers live", () => {
    const canvas = start(new CanvasSse("alpha", {}));
    active()[0]!.emit("intent_pending", { count: 4 });
    active()[0]!.emit("ingests", [{ slug: "pump" }]);
    const onPending = vi.fn();
    const onIngests = vi.fn();
    const intents = start(new IntentsSse({ onPending }));
    start(new IngestsSse({ onIngests }));
    expect(onPending).toHaveBeenCalledWith(4);
    expect(onIngests).toHaveBeenCalledWith([{ slug: "pump" }]);
    intents.disconnect();
    canvas.disconnect();
    active()[0]!.emit("ingests", []);
    expect(onIngests).toHaveBeenLastCalledWith([]);
  });

  it("reconnects once for all consumers and cancels retries on final cleanup", () => {
    const onError = vi.fn();
    const canvas = start(new CanvasSse("alpha", { onError }));
    const intents = start(new IntentsSse({ onError }));
    const ingests = start(new IngestsSse({ onError }));
    active()[0]!.onerror?.(new Event("error"));
    expect(onError).toHaveBeenCalledTimes(3);
    expect(active()).toHaveLength(0);
    vi.advanceTimersByTime(1000);
    expect(active()).toHaveLength(1);
    expect(FakeEventSource.instances).toHaveLength(2);
    active()[0]!.onerror?.(new Event("error"));
    canvas.disconnect();
    intents.disconnect();
    ingests.disconnect();
    vi.advanceTimersByTime(60000);
    expect(active()).toHaveLength(0);
  });

  it("a monitor needs only its canvas subscription and preserves its presence label", () => {
    start(new CanvasSse("wall", {}, { actorLabel: "monitor" }));
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(new URL(active()[0]!.url, "http://localhost").searchParams.get("actor_label")).toBe("monitor");
  });

  it("two tab module realms with three consumers each use two connections", async () => {
    connectionLimit = 2;
    start(new CanvasSse("alpha", {}));
    start(new IntentsSse({}));
    start(new IngestsSse({}));
    // A browser tab has its own module singleton; reset the module cache to
    // model that second realm while the first tab remains connected.
    vi.resetModules();
    const secondCanvas = await import("./sseClient");
    const secondIntents = await import("./intentsSse");
    const secondIngests = await import("./ingestsSse");
    start(new secondCanvas.CanvasSse("beta", {}));
    start(new secondIntents.IntentsSse({}));
    start(new secondIngests.IngestsSse({}));
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(active()).toHaveLength(2);
  });
});
