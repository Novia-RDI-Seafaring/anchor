/**
 * IntentsSse tests (#323) — the push half of the intents queue transport.
 *
 * Pins: the stream address, the `intent_pending {count}` parse, malformed
 * payloads being ignored, the reconnect-with-backoff on error (mirroring
 * CanvasSse / IngestsSse), and the no-EventSource fallback guard.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntentsSse } from "./intentsSse";

type Listener = (ev: MessageEvent) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onerror: ((err: Event) => void) | null = null;
  closed = false;
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: Listener) {
    (this.listeners[type] ??= []).push(fn);
  }

  emit(type: string, data: string) {
    for (const fn of this.listeners[type] ?? []) fn({ data } as MessageEvent);
  }

  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("IntentsSse", () => {
  it("connects to the intents event stream and delivers the pending count", () => {
    const onPending = vi.fn();
    const sse = new IntentsSse({ onPending });
    sse.connect();

    const es = FakeEventSource.instances[0]!;
    expect(es.url).toContain("/api/intents/events");

    es.emit("intent_pending", JSON.stringify({ count: 3 }));
    expect(onPending).toHaveBeenCalledWith(3);

    sse.disconnect();
    expect(es.closed).toBe(true);
  });

  it("ignores malformed payloads and defaults a missing count to 0", () => {
    const onPending = vi.fn();
    const sse = new IntentsSse({ onPending });
    sse.connect();

    const es = FakeEventSource.instances[0]!;
    es.emit("intent_pending", "not json");
    expect(onPending).not.toHaveBeenCalled();

    es.emit("intent_pending", JSON.stringify({}));
    expect(onPending).toHaveBeenCalledWith(0);
    sse.disconnect();
  });

  it("reconnects with backoff after an error", () => {
    vi.useFakeTimers();
    const onError = vi.fn();
    const sse = new IntentsSse({ onError });
    sse.connect();

    const first = FakeEventSource.instances[0]!;
    first.onerror?.(new Event("error"));
    expect(onError).toHaveBeenCalled();
    expect(first.closed).toBe(true);

    vi.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(2);
    sse.disconnect();
  });

  it("is a no-op where EventSource does not exist (jsdom / SSR)", () => {
    vi.stubGlobal("EventSource", undefined);
    const sse = new IntentsSse({ onPending: vi.fn() });
    expect(() => sse.connect()).not.toThrow();
    sse.disconnect();
  });
});
